import json
import glob
import numpy as np
import scipy.stats as st
import pandas as pd
import os
import re
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend (safe for batch)
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
PLOTS_DIR = os.path.join(RESULTS_DIR, "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# SCENARIO MAPPING (grade 3 algoritmos × 3 configurações)
# ═══════════════════════════════════════════════════════════════
# Dois formatos de run_id coexistem:
#   Antigo: 99{X}{seed}  → prefix "99X" (3 dígitos)
#   Novo:   10{X}{seed}  → prefix "10X" (3 dígitos)
#
# Ambos mapeiam para os mesmos cenários canônicos.
SCENARIO_MAP = {
    # ── Formato antigo (991-999) ──
    "991": "TE-FPM-LTM",     # TrustEdge com todos os módulos (M1+M2+M3+M4)
    "992": "TE-FPM",          # TrustEdge com predição, sem live/P2P (M1+M2)
    "993": "TE-D",            # TrustEdge Default (apenas M1)
    "994": "K8s-D",           # Kubernetes vanilla (reativo puro)
    "995": "K8s-FPM-LTM",    # Kubernetes com todos os módulos
    "996": "K8s-FPM",         # Kubernetes com predição, sem live/P2P
    "997": "FF-D",            # First-Fit Default (guloso, reativo)
    "998": "FF-FPM",          # First-Fit com predição
    "999": "FF-FPM-LTM",     # First-Fit com todos os módulos
    # ── Formato novo (101-106) ──
    "101": "TE-D",            # TrustEdge Default (sem M2/M3/M4)
    "102": "TE-FPM",          # TrustEdge + Predição (sem M3/M4)
    "103": "K8s-FPM",         # K8s + Predição (sem M3/M4)
    "104": "FF-D",            # First-Fit Default
    "105": "FF-FPM",          # First-Fit + Predição
    "106": "FF-FPM-LTM",     # First-Fit + Predição + Live/P2P
}

PALETTE = {
    # TrustEdge (tons de verde)
    "TE-FPM-LTM":    "#27ae60",
    "TE-FPM":         "#2ecc71",
    "TE-D":           "#a9dfbf",
    # Kubernetes (tons de roxo/laranja)
    "K8s-D":          "#9b59b6",
    "K8s-FPM":        "#c39bd3",
    "K8s-FPM-LTM":   "#f39c12",
    # First-Fit (tons de azul/vermelho)
    "FF-D":           "#3498db",
    "FF-FPM":         "#85c1e9",
    "FF-FPM-LTM":    "#e74c3c",
}

# Ordem canônica para todos os gráficos (agrupada por configuração)
SCENARIO_ORDER = [
    # Default (sem módulos extras)
    "TE-D", "K8s-D", "FF-D",
    # +FPM (com predição)
    "TE-FPM", "K8s-FPM", "FF-FPM",
    # +FPM+LTM (todos os módulos)
    "TE-FPM-LTM", "K8s-FPM-LTM", "FF-FPM-LTM",
]

# Comparações pareadas relevantes (evitar explosão combinatória)
PAIRWISE_COMPARISONS = [
    # Dentro de cada algoritmo (efeito dos módulos)
    ("TE-D", "TE-FPM"),
    ("TE-FPM", "TE-FPM-LTM"),
    ("TE-D", "TE-FPM-LTM"),
    ("K8s-D", "K8s-FPM"),
    ("K8s-FPM", "K8s-FPM-LTM"),
    ("K8s-D", "K8s-FPM-LTM"),
    ("FF-D", "FF-FPM"),
    ("FF-FPM", "FF-FPM-LTM"),
    ("FF-D", "FF-FPM-LTM"),
    # Entre algoritmos (mesma configuração)
    ("TE-D", "K8s-D"),
    ("TE-D", "FF-D"),
    ("K8s-D", "FF-D"),
    ("TE-FPM", "K8s-FPM"),
    ("TE-FPM", "FF-FPM"),
    ("K8s-FPM", "FF-FPM"),
    ("TE-FPM-LTM", "K8s-FPM-LTM"),
    ("TE-FPM-LTM", "FF-FPM-LTM"),
    ("K8s-FPM-LTM", "FF-FPM-LTM"),
]

CONFIDENCE_LEVEL = 0.95

# Estilo global para publicação
plt.rcParams.update({
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
    """Classifica um arquivo de resultado no cenário correto.
    
    Suporta dois formatos de run_id:
      - Antigo: metrics_run_99X{seed}.json  (ex: 9915000 → prefix "991")
      - Novo:   metrics_run_10X{seed}.json  (ex: 1015000 → prefix "101")
    """
    match = re.search(r'metrics_run_(\d+)\.json', filename)
    if not match:
        return "Unknown"
    
    run_id = match.group(1)
    
    # Tentar prefixo de 3 dígitos para todos os formatos conhecidos
    if len(run_id) >= 3:
        prefix3 = run_id[:3]
        if prefix3 in SCENARIO_MAP:
            return SCENARIO_MAP[prefix3]
    
    return "Unknown"


def load_metrics():
    path = os.path.join(RESULTS_DIR, "metrics_run_*.json")
    print(f"🔍 Searching data in: {path}")
    files = glob.glob(path)
    if not files:
        print("   ⚠️ No files found.")
        return {}, {}

    print(f"   ✅ Found {len(files)} files. Grouping by scenario...")

    grouped_data = {}   # {scenario: [flat_dicts]}
    grouped_raw  = {}   # {scenario: [full_json]}   ← para breakdown

    for f in files:
        scenario = detect_scenario(os.path.basename(f))
        if scenario == "Unknown":
            continue
        grouped_data.setdefault(scenario, [])
        grouped_raw.setdefault(scenario, [])

        try:
            with open(f, 'r') as fh:
                content = json.load(fh)

                flat = {
                    "downtime":        content["sla"]["total_perceived_downtime"],
                    "sla_violations":  content["sla"]["total_delay_sla_violations"],
                    "avg_delay":       content["sla"].get("avg_delay", 0),
                    "exec_overhead_ms": content.get("execution", {}).get("avg_time_per_step_seconds", 0) * 1000,
                    "migrations":      content["provisioning_and_migration"]["total_migrations"],
                    "precision":       content.get("prediction_quality", {}).get("precision", 0),
                    "recall":          content.get("prediction_quality", {}).get("recall", 0),
                }
                grouped_data[scenario].append(flat)
                grouped_raw[scenario].append(content)
        except Exception as e:
            print(f"   ❌ Error reading {os.path.basename(f)}: {e}")

    # Resumo do carregamento
    print(f"\n   Scenarios loaded:")
    for s in SCENARIO_ORDER:
        if s in grouped_data:
            print(f"      {s:<15} → {len(grouped_data[s])} runs")

    return grouped_data, grouped_raw


# ============================================================================
# STATISTICS
# ============================================================================
def calculate_stats(data_list):
    df = pd.DataFrame(data_list)
    stats = {}
    if df.empty:
        return stats, df

    for col in df.columns:
        arr = df[col].values
        n = len(arr)
        mean = np.mean(arr)
        std  = np.std(arr, ddof=1) if n > 1 else 0.0

        if n < 2 or std == 0:
            margin = 0.0
        else:
            se = st.sem(arr)
            ci = st.t.interval(CONFIDENCE_LEVEL, df=n - 1, loc=mean, scale=se)
            margin = ci[1] - mean

        stats[col] = {"mean": mean, "std_dev": std, "ci": margin, "n": n}

    return stats, df


# ============================================================================
# HYPOTHESIS TESTS
# ============================================================================
def run_hypothesis_tests(grouped_data):
    """Executa testes de hipótese apenas para os pares em PAIRWISE_COMPARISONS."""
    available = [s for s in SCENARIO_ORDER if s in grouped_data]
    if len(available) < 2:
        print("⚠️ Need at least 2 scenarios for comparison.")
        return

    metrics_to_test = ["downtime", "sla_violations", "migrations", "precision", "recall"]

    print(f"\n{'='*115}")
    print("HYPOTHESIS TESTS (Pairwise Comparisons)")
    print(f"{'='*115}")

    for s1, s2 in PAIRWISE_COMPARISONS:
        if s1 not in grouped_data or s2 not in grouped_data:
            continue

        df1 = pd.DataFrame(grouped_data[s1])
        df2 = pd.DataFrame(grouped_data[s2])

        print(f"\n--- {s1} vs {s2} ---")
        print(f"{'Metric':<20} | {'Test':<18} | {'p-value':<14} | {'Cohen d':<22} | {'Result':<20}")
        print("-" * 115)

        for metric in metrics_to_test:
            d1 = df1[metric].values
            d2 = df2[metric].values

            # Normality (Shapiro-Wilk)
            _, p1 = st.shapiro(d1)
            _, p2 = st.shapiro(d2)
            is_normal = p1 > 0.05 and p2 > 0.05

            if is_normal:
                stat, pval = st.ttest_ind(d1, d2)
                test_name = "Student t-test"
            else:
                stat, pval = st.mannwhitneyu(d1, d2, alternative='two-sided')
                test_name = "Mann-Whitney U"

            # Cohen's d
            pooled = np.sqrt((np.std(d1, ddof=1)**2 + np.std(d2, ddof=1)**2) / 2)
            d_val = abs(np.mean(d1) - np.mean(d2)) / pooled if pooled > 0 else 0

            if   d_val >= 0.8: eff = "large"
            elif d_val >= 0.5: eff = "medium"
            elif d_val >= 0.2: eff = "small"
            else:              eff = "negligible"

            if pval < 0.001:
                pval_str = f"< 0.001"
            else:
                pval_str = f"{pval:.4f}"

            d_display = f"d={min(d_val, 99.99):.2f}"

            sig = "✅ SIGNIFICANT" if pval < 0.05 else "❌ NOT significant"
            print(f"{metric:<20} | {test_name:<18} | {pval_str:<14} | {d_display} ({eff:<10}) | {sig}")

    # Gerar tabela LaTeX
    _generate_latex_table(grouped_data, metrics_to_test)


def _generate_latex_table(grouped_data, metrics_to_test):
    """Gera tabela LaTeX pronta para o paper."""
    print(f"\n{'='*80}")
    print("LATEX TABLE (Copy-paste into your paper)")
    print(f"{'='*80}")
    print(r"\begin{table}[htbp]")
    print(r"\centering")
    print(r"\caption{Pairwise statistical comparison.}")
    print(r"\label{tab:hypothesis_tests}")
    print(r"\begin{tabular}{llccc}")
    print(r"\hline")
    print(r"\textbf{Comparison} & \textbf{Metric} & \textbf{Test} & \textbf{p-value} & \textbf{Cohen's d} \\")
    print(r"\hline")

    for s1, s2 in PAIRWISE_COMPARISONS:
        if s1 not in grouped_data or s2 not in grouped_data:
            continue

        df1 = pd.DataFrame(grouped_data[s1])
        df2 = pd.DataFrame(grouped_data[s2])
        comp_label = f"{s1} vs {s2}"

        for k, metric in enumerate(metrics_to_test):
            d1 = df1[metric].values
            d2 = df2[metric].values

            _, p1 = st.shapiro(d1)
            _, p2 = st.shapiro(d2)
            is_normal = p1 > 0.05 and p2 > 0.05

            if is_normal:
                _, pval = st.ttest_ind(d1, d2)
                test_name = "t-test"
            else:
                _, pval = st.mannwhitneyu(d1, d2, alternative='two-sided')
                test_name = "M-W U"

            pooled = np.sqrt((np.std(d1, ddof=1)**2 + np.std(d2, ddof=1)**2) / 2)
            d_val = abs(np.mean(d1) - np.mean(d2)) / pooled if pooled > 0 else 0

            pval_str = "$< 0.001$" if pval < 0.001 else f"${pval:.3f}$"
            d_str = f"${min(d_val, 99.99):.2f}$"

            label = comp_label if k == 0 else ""
            metric_clean = metric.replace("_", " ").title()

            print(f"{label} & {metric_clean} & {test_name} & {pval_str} & {d_str} \\\\")

        print(r"\hline")

    print(r"\end{tabular}")
    print(r"\end{table}")

# ============================================================================
# PLOT HELPERS
# ============================================================================
def _ordered(all_stats):
    """Returns scenarios in canonical order that exist in all_stats."""
    return [s for s in SCENARIO_ORDER if s in all_stats]


def _save(fig, filename):
    path = os.path.join(PLOTS_DIR, filename)
    fig.savefig(path)
    print(f"   📊 Saved: {path}")
    plt.close(fig)


# ============================================================================
# PLOT 1 – Bar charts with error bars (one per metric)
# ============================================================================
def plot_bar(all_stats, metric, ylabel, title, fname):
    scenarios = _ordered(all_stats)
    means = [all_stats[s][metric]["mean"] for s in scenarios]
    cis   = [all_stats[s][metric]["ci"]   for s in scenarios]
    colors = [PALETTE[s] for s in scenarios]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(scenarios, means, yerr=cis, capsize=6,
                  color=colors, edgecolor='black', alpha=0.85)

    for bar, m in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f'{m:.1f}', ha='center', va='bottom', fontweight='bold', fontsize=8)

    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    plt.xticks(rotation=30, ha='right')
    _save(fig, fname)


# ============================================================================
# PLOT 2 – Box plots (distribution visibility)
# ============================================================================
def plot_boxplots(grouped_data):
    metrics_cfg = [
        ("downtime",       "Perceived Downtime (steps)",  "Downtime Distribution"),
        ("sla_violations", "SLA Violations",              "SLA Violations Distribution"),
        ("migrations",     "Total Migrations",            "Migration Count Distribution"),
    ]

    for metric, ylabel, title in metrics_cfg:
        fig, ax = plt.subplots(figsize=(10, 6))
        data_to_plot = []
        labels = []
        colors_list = []

        for s in SCENARIO_ORDER:
            if s not in grouped_data:
                continue
            vals = [d[metric] for d in grouped_data[s]]
            data_to_plot.append(vals)
            labels.append(s)
            colors_list.append(PALETTE[s])

        bp = ax.boxplot(data_to_plot, labels=labels, patch_artist=True,
                        widths=0.5, showmeans=True,
                        meanprops=dict(marker='D', markerfacecolor='white', markersize=6))

        for patch, color in zip(bp['boxes'], colors_list):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)

        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        plt.xticks(rotation=30, ha='right')
        _save(fig, f"boxplot_{metric}.png")


# ============================================================================
# PLOT 3 – Pareto front (Migrations vs Downtime)
# ============================================================================
def plot_pareto_front(all_stats):
    scenarios = _ordered(all_stats)
    fig, ax = plt.subplots(figsize=(9, 7))

    for s in scenarios:
        x    = all_stats[s]["migrations"]["mean"]
        y    = all_stats[s]["downtime"]["mean"]
        xerr = all_stats[s]["migrations"]["ci"]
        yerr = all_stats[s]["downtime"]["ci"]

        ax.errorbar(x, y, xerr=xerr, yerr=yerr,
                    fmt='o', markersize=12, capsize=6, color=PALETTE[s],
                    label=s, elinewidth=2, markeredgecolor='black')
        ax.annotate(s, (x, y), textcoords="offset points",
                    xytext=(12, 10), fontsize=9, fontweight='bold')

    ax.set_xlabel("Total Migrations (lower is better)")
    ax.set_ylabel("Perceived Downtime (steps, lower is better)")
    ax.set_title("Migration Cost vs. Service Availability")
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.annotate("← Ideal", xy=(0.02, 0.02), xycoords='axes fraction',
                fontsize=12, color='green', fontstyle='italic')
    _save(fig, "pareto_front.png")


# ============================================================================
# PLOT 4 – Precision-Recall with F1 iso-lines
# ============================================================================
def plot_precision_recall(all_stats):
    scenarios = _ordered(all_stats)
    fig, ax = plt.subplots(figsize=(8, 6))

    # F1 iso-lines
    for f1 in [0.2, 0.4, 0.6, 0.8]:
        r = np.linspace(0.01, 1.0, 200)
        p = (f1 * r) / (2 * r - f1)
        valid = (p > 0) & (p <= 1)
        ax.plot(r[valid] * 100, p[valid] * 100, '--', color='gray', alpha=0.35, lw=1)
        idx = np.argmin(np.abs(r[valid] - 0.85))
        ax.annotate(f'F1={f1}', xy=(r[valid][idx] * 100, p[valid][idx] * 100),
                    fontsize=8, color='gray')

    for s in scenarios:
        rec  = all_stats[s]["recall"]["mean"]
        prec = all_stats[s]["precision"]["mean"]
        # Skip scenarios with 0/0 precision/recall
        if rec == 0 and prec == 0:
            continue
        ax.scatter(rec, prec, s=220, color=PALETTE[s], label=s,
                   zorder=5, edgecolors='black', linewidths=1.2)
        ax.annotate(s, (rec, prec), textcoords="offset points",
                    xytext=(10, 10), fontsize=9, fontweight='bold')

    ax.set_xlabel("Recall (%)")
    ax.set_ylabel("Precision (%)")
    ax.set_title("Prediction Quality: Precision vs. Recall")
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 105)
    ax.legend(fontsize=8)
    ax.grid(True, linestyle='--', alpha=0.5)
    _save(fig, "precision_recall.png")


# ============================================================================
# PLOT 5 – Radar / Spider chart (multi-metric overview)
# ============================================================================
def plot_radar(all_stats):
    scenarios = _ordered(all_stats)

    radar_metrics = [
        ("downtime",       "Downtime",    True),
        ("sla_violations", "SLA Viol.",   True),
        ("migrations",     "Migrations",  True),
        ("precision",      "Precision",   False),
        ("recall",         "Recall",      False),
        ("avg_delay",      "Avg Delay",   True),
    ]

    labels = [m[1] for m in radar_metrics]
    N = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    raw = {}
    for key, _, _ in radar_metrics:
        vals = [all_stats[s][key]["mean"] for s in scenarios]
        raw[key] = {"min": min(vals), "max": max(vals)}

    for s in scenarios:
        values = []
        for key, _, invert in radar_metrics:
            v = all_stats[s][key]["mean"]
            mn, mx = raw[key]["min"], raw[key]["max"]
            rng = mx - mn if mx != mn else 1
            norm = (v - mn) / rng
            if invert:
                norm = 1 - norm
            values.append(norm)

        values += values[:1]
        ax.plot(angles, values, 'o-', label=s, color=PALETTE[s], linewidth=2)
        ax.fill(angles, values, color=PALETTE[s], alpha=0.05)

    ax.set_thetagrids([a * 180 / np.pi for a in angles[:-1]], labels)
    ax.set_ylim(0, 1.05)
    ax.set_title("Multi-Metric Overview\n(outer = better)", pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.45, 1.1), fontsize=8)
    _save(fig, "radar_overview.png")


# ============================================================================
# PLOT 6 – Downtime breakdown (stacked bar)
# ============================================================================
def plot_downtime_breakdown(grouped_raw):
    scenarios = [s for s in SCENARIO_ORDER if s in grouped_raw]

    categories = ["Provisioning", "Migration", "Server Failure", "Other"]
    cat_colors = ["#f39c12", "#3498db", "#e74c3c", "#95a5a6"]

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(scenarios))
    width = 0.5

    bottoms = np.zeros(len(scenarios))

    for cat_idx, cat_name in enumerate(categories):
        heights = []
        for s in scenarios:
            cat_total = 0
            for raw in grouped_raw[s]:
                bd = raw.get("provisioning_and_migration", {}).get("downtime_breakdown", {})
                if cat_name == "Provisioning":
                    cat_total += bd.get("provisionings", {}).get("total", 0)
                elif cat_name == "Migration":
                    cat_total += bd.get("migrations", {}).get("total", 0)
                elif cat_name == "Server Failure":
                    cat_total += bd.get("server_failures", {}).get("total", 0)
                else:
                    total_perc = raw["sla"]["total_perceived_downtime"]
                    tracked = (bd.get("provisionings", {}).get("total", 0)
                             + bd.get("migrations", {}).get("total", 0)
                             + bd.get("server_failures", {}).get("total", 0))
                    cat_total += max(0, total_perc - tracked)

            n = len(grouped_raw[s])
            heights.append(cat_total / n if n > 0 else 0)

        ax.bar(x, heights, width, bottom=bottoms, label=cat_name,
               color=cat_colors[cat_idx], edgecolor='black', alpha=0.85)
        bottoms += np.array(heights)

    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=30, ha='right')
    ax.set_ylabel("Downtime (steps)")
    ax.set_title("Downtime Breakdown by Cause")
    ax.legend()
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    _save(fig, "downtime_breakdown.png")


# ============================================================================
# PLOT 7 – Migration breakdown by reason (stacked bar)
# ============================================================================
def plot_migration_breakdown(grouped_raw):
    scenarios = [s for s in SCENARIO_ORDER if s in grouped_raw]

    reasons = [
        ("delay_violation",          "SLA Violation",     "#f1c40f"),
        ("low_reliability",          "Low Reliability",   "#e67e22"),
        ("predicted_failure",        "Predicted Failure",  "#2ecc71"),
        ("server_failed_unpredicted","Cold Migration (FN)","#e74c3c"),
    ]

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(scenarios))
    width = 0.5
    bottoms = np.zeros(len(scenarios))

    for reason_key, reason_label, color in reasons:
        heights = []
        for s in scenarios:
            total = 0
            for raw in grouped_raw[s]:
                by_reason = raw.get("provisioning_and_migration", {}).get(
                    "migrations_by_original_reason", {})
                total += by_reason.get(reason_key, 0)
            n = len(grouped_raw[s])
            heights.append(total / n if n > 0 else 0)

        ax.bar(x, heights, width, bottom=bottoms, label=reason_label,
               color=color, edgecolor='black', alpha=0.85)
        bottoms += np.array(heights)

    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=30, ha='right')
    ax.set_ylabel("Average Migrations")
    ax.set_title("Migration Breakdown by Trigger Reason")
    ax.legend(fontsize=9)
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    _save(fig, "migration_breakdown.png")


# ============================================================================
# PLOT 8 – Grouped bar chart (modular comparison, estilo Lancer Fig.4)
# ============================================================================
def plot_modular_comparison(all_stats, metric, ylabel, title, fname):
    """Gráfico de barras agrupadas: 3 algoritmos × 3 configurações."""
    algorithms = ["TE", "K8s", "FF"]
    configs = ["D", "FPM", "FPM-LTM"]
    config_labels = ["Default", "+FPM", "+FPM+LTM"]

    # Cores por algoritmo
    algo_colors = {
        "TE":  ["#a9dfbf", "#2ecc71", "#27ae60"],
        "K8s": ["#d7bde2", "#c39bd3", "#9b59b6"],
        "FF":  ["#aed6f1", "#85c1e9", "#3498db"],
    }

    fig, ax = plt.subplots(figsize=(10, 6))

    n_configs = len(configs)
    n_algos = len(algorithms)
    bar_width = 0.22
    group_width = n_algos * bar_width + 0.1

    for ci, config in enumerate(configs):
        for ai, algo in enumerate(algorithms):
            scenario_name = f"{algo}-{config}"
            if scenario_name not in all_stats:
                continue

            x_pos = ci * (group_width + 0.3) + ai * (bar_width + 0.02)
            mean_val = all_stats[scenario_name][metric]["mean"]
            ci_val = all_stats[scenario_name][metric]["ci"]

            bar = ax.bar(x_pos, mean_val, bar_width, yerr=ci_val, capsize=4,
                         color=algo_colors[algo][ci], edgecolor='black', alpha=0.85,
                         label=f"{algo}" if ci == 0 else "")

            ax.text(x_pos, mean_val + ci_val + 0.02 * max(1, mean_val),
                    f'{mean_val:.0f}', ha='center', va='bottom', fontsize=7,
                    fontweight='bold')

    # X-axis labels (por configuração)
    group_centers = []
    for ci in range(n_configs):
        center = ci * (group_width + 0.3) + (n_algos - 1) * (bar_width + 0.02) / 2
        group_centers.append(center)

    ax.set_xticks(group_centers)
    ax.set_xticklabels(config_labels, fontweight='bold')

    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    # Legenda customizada (apenas 1 entrada por algoritmo)
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#2ecc71', edgecolor='black', label='TrustEdge'),
        Patch(facecolor='#9b59b6', edgecolor='black', label='Kubernetes'),
        Patch(facecolor='#3498db', edgecolor='black', label='First-Fit'),
    ]
    ax.legend(handles=legend_elements, loc='upper right')

    _save(fig, fname)


# ============================================================================
# MAIN
# ============================================================================
def main():
    grouped_data, grouped_raw = load_metrics()
    if not grouped_data:
        print("No data to analyze.")
        return

    all_stats = {}

    # ── Console table ──
    print(f"\n{'='*100}")
    print(f"{'SCENARIO':<15} | {'METRIC':<20} | {'MEAN':<12} | {'STD DEV':<10} | {'95% CI (±)':<12}")
    print(f"{'='*100}")

    for scenario in SCENARIO_ORDER:
        if scenario not in grouped_data:
            continue
        stats, _ = calculate_stats(grouped_data[scenario])
        all_stats[scenario] = stats
        for metric, val in stats.items():
            print(f"{scenario:<15} | {metric:<20} | {val['mean']:<12.4f} | {val['std_dev']:<10.4f} | ±{val['ci']:<12.4f}")
        print("-" * 100)

    # ── Hypothesis tests ──
    run_hypothesis_tests(grouped_data)

    # ── Plots ──
    print("\n🎨 Generating plots...")

    # 1. Bar charts (individual metrics)
    plot_bar(all_stats, "downtime",       "Time Steps",       "Perceived Downtime (lower is better)",     "bar_downtime.png")
    plot_bar(all_stats, "sla_violations", "Violations",       "SLA Violations (lower is better)",         "bar_sla_violations.png")
    plot_bar(all_stats, "migrations",     "Total Migrations", "Migration Count (lower is better)",        "bar_migrations.png")
    plot_bar(all_stats, "exec_overhead_ms","Time (ms/step)",  "Avg Execution Overhead per Step",          "bar_overhead.png")
    plot_bar(all_stats, "avg_delay",      "Delay (ms)",       "Average End-to-End Delay",                 "bar_avg_delay.png")

    # 2. Box plots
    plot_boxplots(grouped_data)

    # 3. Pareto front
    plot_pareto_front(all_stats)

    # 4. Precision-Recall
    plot_precision_recall(all_stats)

    # 5. Radar
    plot_radar(all_stats)

    # 6. Downtime breakdown
    plot_downtime_breakdown(grouped_raw)

    # 7. Migration breakdown
    plot_migration_breakdown(grouped_raw)

    # 8. Modular comparison (estilo Lancer Fig.4)
    plot_modular_comparison(all_stats, "sla_violations", "SLA Violations",
                           "SLA Violations by Algorithm and Module Configuration",
                           "modular_sla_violations.png")
    plot_modular_comparison(all_stats, "downtime", "Downtime (steps)",
                           "Downtime by Algorithm and Module Configuration",
                           "modular_downtime.png")
    plot_modular_comparison(all_stats, "migrations", "Total Migrations",
                           "Migrations by Algorithm and Module Configuration",
                           "modular_migrations.png")

    print(f"\n✅ All outputs saved to: {PLOTS_DIR}")
    print("   Use these in your paper's 'Results and Discussion' section.")


if __name__ == "__main__":
    main()