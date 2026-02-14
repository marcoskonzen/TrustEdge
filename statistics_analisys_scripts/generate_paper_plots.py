"""
Gera TODOS os gráficos de resultados para o paper.
Dados: 991 (TE-Best), 992 (TE-Worst), 993 (TE-Tradeoff),
       994 (K8s-Baseline), 995 (K8s-Enhanced).

Gráficos gerados:
  1. boxplot_downtime.pdf
  2. boxplot_sla_violations.pdf
  3. boxplot_migrations.pdf
  4. precision_recall.pdf
  5. pareto_dt_sla.pdf
  6. pareto_dt_migrations.pdf
"""
import json
import glob
import numpy as np
import scipy.stats as st
import pandas as pd
import os
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
PLOTS_DIR = os.path.join(PROJECT_ROOT, "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)

SCENARIO_MAP = {
    "991": "TE-Best",
    "992": "TE-Worst",
    "993": "TE-Tradeoff",
    "994": "K8s-Baseline",
    "995": "K8s-Enhanced",
}

PALETTE = {
    "TE-Best":       "#27ae60",
    "TE-Tradeoff":   "#2ecc71",
    "TE-Worst":      "#a9dfbf",
    "K8s-Baseline":  "#9b59b6",
    "K8s-Enhanced":  "#f39c12",
}

MARKERS = {
    "TE-Best":       "^",
    "TE-Tradeoff":   "s",
    "TE-Worst":      "v",
    "K8s-Baseline":  "o",
    "K8s-Enhanced":  "D",
}

CONFIDENCE_LEVEL = 0.95

# Estilo global — idêntico para todos os gráficos
plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 11,
    'axes.titlesize': 13,
    'axes.labelsize': 12,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
})


# ============================================================================
# DATA LOADING
# ============================================================================
def detect_scenario(filename):
    """Identifica cenário pelo prefixo do run_id (991-995)."""
    match = re.search(r'metrics_run_(\d+)\.json', filename)
    if not match:
        return None
    prefix = match.group(1)[:3]
    return SCENARIO_MAP.get(prefix, None)


def load_metrics():
    """Carrega todos os JSONs de resultados para os 5 cenários do paper."""
    path = os.path.join(RESULTS_DIR, "metrics_run_*.json")
    files = glob.glob(path)
    print(f"🔍 Found {len(files)} total JSON files in results/")

    grouped_data = {}
    loaded = 0
    skipped = 0

    for f in sorted(files):
        scenario = detect_scenario(os.path.basename(f))
        if scenario is None:
            skipped += 1
            continue

        grouped_data.setdefault(scenario, [])

        try:
            with open(f, 'r') as fh:
                content = json.load(fh)
                flat = {
                    "downtime":       content["sla"]["total_perceived_downtime"],
                    "sla_violations": content["sla"]["total_delay_sla_violations"],
                    "avg_delay":      content["sla"].get("avg_delay", 0),
                    "migrations":     content["provisioning_and_migration"]["total_migrations"],
                    "precision":      content.get("prediction_quality", {}).get("precision", 0),
                    "recall":         content.get("prediction_quality", {}).get("recall", 0),
                }
                grouped_data[scenario].append(flat)
                loaded += 1
        except Exception as e:
            print(f"   ❌ Error: {os.path.basename(f)}: {e}")

    print(f"   ✅ Loaded {loaded} files (skipped {skipped})")
    for s in sorted(grouped_data.keys()):
        print(f"      {s:<15} → {len(grouped_data[s])} runs")

    return grouped_data


def calculate_stats(data_list):
    """Calcula média, desvio padrão e IC 95% para cada métrica."""
    df = pd.DataFrame(data_list)
    stats = {}
    for col in df.columns:
        arr = df[col].values
        n = len(arr)
        mean = np.mean(arr)
        std = np.std(arr, ddof=1) if n > 1 else 0.0
        if n < 2 or std == 0:
            margin = 0.0
        else:
            se = st.sem(arr)
            ci = st.t.interval(CONFIDENCE_LEVEL, df=n - 1, loc=mean, scale=se)
            margin = ci[1] - mean
        stats[col] = {"mean": mean, "std_dev": std, "ci": margin, "n": n}
    return stats


def get_sorted_scenarios(grouped_data, metric, reverse=True):
    """Ordena cenários por média do metric (reverse=True: pior primeiro)."""
    means = {}
    for scenario, data_list in grouped_data.items():
        vals = [d[metric] for d in data_list]
        means[scenario] = np.mean(vals)
    return sorted(means.keys(), key=lambda s: means[s], reverse=reverse)


def save_figure(fig, basename):
    """Salva figura em PNG e PDF."""
    png_path = os.path.join(PLOTS_DIR, basename)
    pdf_path = png_path.replace(".png", ".pdf")
    fig.savefig(png_path, dpi=300, bbox_inches='tight')
    fig.savefig(pdf_path, bbox_inches='tight')
    print(f"   📊 Saved: {basename} (.png + .pdf)")
    plt.close(fig)


# ============================================================================
# BOXPLOTS
# ============================================================================
def plot_boxplot(grouped_data, metric, ylabel, title, filename):
    """Boxplot genérico: cenários ordenados pior→melhor (esquerda→direita)."""
    order = get_sorted_scenarios(grouped_data, metric, reverse=True)
    fig, ax = plt.subplots(figsize=(10, 6))

    data_to_plot = []
    labels = []
    colors_list = []

    for s in order:
        if s not in grouped_data:
            continue
        vals = [d[metric] for d in grouped_data[s]]
        data_to_plot.append(vals)
        labels.append(s)
        colors_list.append(PALETTE[s])

    bp = ax.boxplot(
        data_to_plot, labels=labels, patch_artist=True,
        widths=0.5, showmeans=True,
        meanprops=dict(marker='D', markerfacecolor='white',
                       markeredgecolor='black', markersize=6),
    )

    for patch, color in zip(bp['boxes'], colors_list):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    for element in ['whiskers', 'caps']:
        for line in bp[element]:
            line.set_color('#555555')
    for line in bp['medians']:
        line.set_color('#333333')
        line.set_linewidth(1.5)

    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    plt.xticks(rotation=15, ha='right')

    save_figure(fig, filename)


# ============================================================================
# PRECISION-RECALL
# ============================================================================
def plot_precision_recall(all_stats):
    """Scatter de Precision vs Recall com iso-linhas de F1."""
    fig, ax = plt.subplots(figsize=(8, 6))

    # Iso-linhas de F1
    for f1 in [0.2, 0.4, 0.6, 0.8]:
        r = np.linspace(0.01, 1.0, 200)
        p = (f1 * r) / (2 * r - f1)
        valid = (p > 0) & (p <= 1)
        ax.plot(r[valid] * 100, p[valid] * 100, '--', color='gray',
                alpha=0.35, lw=1)
        idx = np.argmin(np.abs(r[valid] - 0.85))
        ax.annotate(f'F1={f1}', xy=(r[valid][idx] * 100, p[valid][idx] * 100),
                    fontsize=8, color='gray')

    offsets = {
        "TE-Best":       (10, -15),
        "TE-Worst":      (10, -15),
        "TE-Tradeoff":   (10, 10),
        "K8s-Enhanced":  (-80, 10),
        "K8s-Baseline":  (10, 10),
    }

    for s in sorted(all_stats.keys()):
        rec = all_stats[s]["recall"]["mean"]
        prec = all_stats[s]["precision"]["mean"]
        if rec == 0 and prec == 0:
            ax.scatter(0, 0, s=220, color=PALETTE[s],
                       label=f"{s} (no prediction)",
                       zorder=5, edgecolors='black', linewidths=1.2,
                       marker='x')
            continue

        ax.scatter(rec, prec, s=220, color=PALETTE[s], label=s,
                   zorder=5, edgecolors='black', linewidths=1.2,
                   marker=MARKERS[s])
        ofs = offsets.get(s, (10, 10))
        ax.annotate(s, (rec, prec), textcoords="offset points",
                    xytext=ofs, fontsize=9, fontweight='bold')

    ax.set_xlabel("Recall (%)")
    ax.set_ylabel("Precision (%)")
    ax.set_title("Prediction Quality: Precision vs. Recall")
    ax.set_xlim(-5, 105)
    ax.set_ylim(-5, 105)
    ax.legend(fontsize=8, loc='lower left')
    ax.grid(True, linestyle='--', alpha=0.5)

    save_figure(fig, "precision_recall.png")


# ============================================================================
# PARETO: Downtime × SLA Violations
# ============================================================================
def plot_pareto_dt_sla(all_stats):
    """Scatter DT vs SLA com barras de erro. Sem annotations/setas."""
    fig, ax = plt.subplots(figsize=(8, 6))

    for s in sorted(all_stats.keys()):
        dt_m = all_stats[s]["downtime"]["mean"]
        dt_e = all_stats[s]["downtime"]["ci"]
        sla_m = all_stats[s]["sla_violations"]["mean"]
        sla_e = all_stats[s]["sla_violations"]["ci"]

        ax.errorbar(
            dt_m, sla_m, xerr=dt_e, yerr=sla_e,
            fmt=MARKERS[s], color=PALETTE[s],
            markersize=10, markeredgecolor='black', markeredgewidth=0.8,
            capsize=4, capthick=1, elinewidth=1,
            label=s, zorder=5,
        )

    ax.set_xlabel("Perceived Downtime (steps, lower is better)")
    ax.set_ylabel("SLA Violations (steps, lower is better)")
    ax.set_title("Trade-off: Downtime vs. SLA Violations")
    ax.legend(fontsize=9, loc='best')
    ax.grid(True, linestyle='--', alpha=0.5)

    save_figure(fig, "pareto_dt_sla.png")


# ============================================================================
# PARETO: Downtime × Migrations
# ============================================================================
def plot_pareto_dt_mig(all_stats):
    """Scatter DT vs Migrations com barras de erro. Sem annotations/setas."""
    fig, ax = plt.subplots(figsize=(8, 6))

    for s in sorted(all_stats.keys()):
        dt_m = all_stats[s]["downtime"]["mean"]
        dt_e = all_stats[s]["downtime"]["ci"]
        mig_m = all_stats[s]["migrations"]["mean"]
        mig_e = all_stats[s]["migrations"]["ci"]

        ax.errorbar(
            dt_m, mig_m, xerr=dt_e, yerr=mig_e,
            fmt=MARKERS[s], color=PALETTE[s],
            markersize=10, markeredgecolor='black', markeredgewidth=0.8,
            capsize=4, capthick=1, elinewidth=1,
            label=s, zorder=5,
        )

    ax.set_xlabel("Perceived Downtime (steps, lower is better)")
    ax.set_ylabel("Total Migrations (lower is better)")
    ax.set_title("Trade-off: Downtime vs. Migrations")
    ax.legend(fontsize=9, loc='best')
    ax.grid(True, linestyle='--', alpha=0.5)

    save_figure(fig, "pareto_dt_migrations.png")


# ============================================================================
# TABELA CONSOLIDADA
# ============================================================================
def print_consolidated_table(all_stats, grouped_data):
    """Imprime tabela consolidada no console + LaTeX."""
    order = get_sorted_scenarios(grouped_data, "downtime", reverse=True)

    print(f"\n{'='*110}")
    print(f"CONSOLIDATED TABLE")
    print(f"{'='*110}")
    fmt_hdr = (f"{'Scenario':<15} | {'Downtime':>14} | {'SLA Viol.':>16} | "
               f"{'Migrations':>14} | {'Avg Delay':>14} | {'Prec.':>8} | "
               f"{'Recall':>8}")
    print(fmt_hdr)
    print(f"{'-'*110}")

    for s in order:
        if s not in all_stats:
            continue
        ss = all_stats[s]
        dt  = f"{ss['downtime']['mean']:.0f} ± {ss['downtime']['ci']:.0f}"
        sla = f"{ss['sla_violations']['mean']:.0f} ± {ss['sla_violations']['ci']:.0f}"
        mig = f"{ss['migrations']['mean']:.0f} ± {ss['migrations']['ci']:.0f}"
        dl  = f"{ss['avg_delay']['mean']:.1f} ± {ss['avg_delay']['ci']:.1f}"
        pr  = f"{ss['precision']['mean']:.1f}%"
        rc  = f"{ss['recall']['mean']:.1f}%"
        print(f"{s:<15} | {dt:>14} | {sla:>16} | {mig:>14} | "
              f"{dl:>14} | {pr:>8} | {rc:>8}")

    print(f"{'='*110}")

    # LaTeX
    print(f"\n% LaTeX table (copy-paste ready):")
    print(r"\begin{table}[!htb]")
    print(r"\footnotesize")
    print(r"\caption{Consolidated results (mean $\pm$ 95\% CI, $n{=}30$).}")
    print(r"\label{tab:results}")
    print(r"\centering")
    print(r"\begin{adjustbox}{max width=\columnwidth}")
    print(r"\begin{tabular}{|l|r|r|r|r|}")
    print(r"\hline")
    print(r"\textbf{Scenario} & \textbf{Downtime} & \textbf{SLA Violations} "
          r"& \textbf{Migrations} & \textbf{Delay (ms)} \\")
    print(r"\hline")

    for s in order:
        if s not in all_stats:
            continue
        ss = all_stats[s]
        dt  = f"${ss['downtime']['mean']:.0f} \\pm {ss['downtime']['ci']:.0f}$"
        sla = f"${ss['sla_violations']['mean']:.0f} \\pm {ss['sla_violations']['ci']:.0f}$"
        mig = f"${ss['migrations']['mean']:.0f} \\pm {ss['migrations']['ci']:.0f}$"
        dl_mean = ss['avg_delay']['mean']
        dl_ci   = ss['avg_delay']['ci']
        dl  = f"${dl_mean:.1f} \\pm {dl_ci:.1f}$".replace(".", "{,}")
        print(f"{s} & {dt} & {sla} & {mig} & {dl} \\\\")

    print(r"\hline")
    print(r"\end{tabular}")
    print(r"\end{adjustbox}")
    print(r"\end{table}")


# ============================================================================
# MAIN
# ============================================================================
def main():
    print("=" * 70)
    print("PAPER PLOTS GENERATOR (unified)")
    print("=" * 70)

    grouped_data = load_metrics()

    if not grouped_data:
        print("❌ No data found.")
        return

    # Compute stats
    all_stats = {}
    for s in grouped_data:
        all_stats[s] = calculate_stats(grouped_data[s])

    # Table
    print_consolidated_table(all_stats, grouped_data)

    # Plots
    print(f"\n🎨 Generating paper plots...")

    plot_boxplot(grouped_data, "downtime",
                 "Perceived Downtime (steps)",
                 "Downtime Distribution",
                 "boxplot_downtime.png")

    plot_boxplot(grouped_data, "sla_violations",
                 "SLA Violations",
                 "SLA Violations Distribution",
                 "boxplot_sla_violations.png")

    plot_boxplot(grouped_data, "migrations",
                 "Total Migrations",
                 "Migration Count Distribution",
                 "boxplot_migrations.png")

    plot_precision_recall(all_stats)
    plot_pareto_dt_sla(all_stats)
    plot_pareto_dt_mig(all_stats)

    print(f"\n✅ All paper plots saved to: {PLOTS_DIR}")
    print("   Files:")
    print("     boxplot_downtime.pdf")
    print("     boxplot_sla_violations.pdf")
    print("     boxplot_migrations.pdf")
    print("     precision_recall.pdf")
    print("     pareto_dt_sla.pdf")
    print("     pareto_dt_migrations.pdf")


if __name__ == "__main__":
    main()