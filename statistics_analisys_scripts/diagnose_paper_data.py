"""
Diagnóstico completo dos dados do paper.
Lê TODOS os JSONs dos 5 cenários originais (991-995) e valida cada valor.
"""
import json
import glob
import numpy as np
import scipy.stats as st
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

SCENARIO_MAP = {
    "991": "TE-Best",
    "992": "TE-Worst",
    "993": "TE-Tradeoff",
    "994": "K8s-Baseline",
    "995": "K8s-Enhanced",
}

CONFIDENCE_LEVEL = 0.95


def main():
    print("=" * 100)
    print("DIAGNÓSTICO COMPLETO - DADOS DO PAPER (5 cenários originais)")
    print("=" * 100)

    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "metrics_run_*.json")))
    print(f"\nTotal de arquivos em results/: {len(files)}")

    # ── 1. Agrupar arquivos por cenário ──
    scenario_files = {}
    skipped = []
    for f in files:
        match = re.search(r'metrics_run_(\d+)\.json', os.path.basename(f))
        if not match:
            continue
        run_id = match.group(1)
        prefix = run_id[:3]
        scenario = SCENARIO_MAP.get(prefix, None)
        if scenario is None:
            skipped.append((run_id, prefix))
            continue
        scenario_files.setdefault(scenario, []).append(f)

    print(f"\nArquivos mapeados para cenários do paper:")
    for s in ["TE-Best", "TE-Tradeoff", "TE-Worst", "K8s-Baseline", "K8s-Enhanced"]:
        n = len(scenario_files.get(s, []))
        print(f"   {s:<15} → {n} arquivos (prefix {[k for k,v in SCENARIO_MAP.items() if v==s][0]})")
    print(f"   Ignorados (não-paper): {len(skipped)} arquivos")

    # ── 2. Ler TODOS os JSONs e extrair métricas ──
    all_data = {}  # scenario → list of dicts
    all_raw = {}   # scenario → list of full JSON

    for scenario, file_list in scenario_files.items():
        all_data[scenario] = []
        all_raw[scenario] = []
        for f in sorted(file_list):
            try:
                with open(f) as fh:
                    content = json.load(fh)

                run_id = re.search(r'metrics_run_(\d+)\.json', os.path.basename(f)).group(1)
                sla = content.get("sla", {})
                prov = content.get("provisioning_and_migration", {})
                pred = content.get("prediction_quality", {})
                params = content.get("parameters", {})
                execution = content.get("execution", {})

                row = {
                    "run_id": run_id,
                    "seed": run_id[3:],  # últimos dígitos
                    "downtime": sla.get("total_perceived_downtime", -1),
                    "sla_violations": sla.get("total_delay_sla_violations", -1),
                    "migrations": prov.get("total_migrations", -1),
                    "avg_delay": sla.get("avg_delay", -1),
                    "precision": pred.get("precision", -1),
                    "recall": pred.get("recall", -1),
                    "window_size": params.get("window_size", "?"),
                    "reliability_threshold": params.get("reliability_threshold", "?"),
                    "lookahead": os.environ.get("TRUSTEDGE_LOOKAHEAD", params.get("lookahead", "?")),
                    "exec_time_min": execution.get("total_time_minutes", -1),
                }
                all_data[scenario].append(row)
                all_raw[scenario].append(content)
            except Exception as e:
                print(f"   ❌ Error reading {os.path.basename(f)}: {e}")

    # ── 3. Análise detalhada por cenário ──
    for scenario in ["TE-Best", "TE-Tradeoff", "TE-Worst", "K8s-Baseline", "K8s-Enhanced"]:
        data = all_data.get(scenario, [])
        if not data:
            print(f"\n{'='*100}")
            print(f"⚠️  {scenario}: SEM DADOS!")
            continue

        print(f"\n{'='*100}")
        print(f"📊 {scenario} ({len(data)} runs)")
        print(f"{'='*100}")

        # Parâmetros (verificar consistência)
        ws_vals = set(d["window_size"] for d in data)
        rt_vals = set(d["reliability_threshold"] for d in data)
        print(f"\n   Parâmetros:")
        print(f"      window_size:           {ws_vals}")
        print(f"      reliability_threshold: {rt_vals}")

        # Métricas individuais
        metrics = ["downtime", "sla_violations", "migrations", "avg_delay", "precision", "recall"]
        print(f"\n   {'Metric':<18} | {'Min':>8} | {'Max':>8} | {'Mean':>8} | {'Std':>8} | {'CI±':>8} | {'CV%':>6}")
        print(f"   {'-'*85}")

        stats_out = {}
        for m in metrics:
            vals = np.array([d[m] for d in data], dtype=float)
            n = len(vals)
            mean = np.mean(vals)
            std = np.std(vals, ddof=1) if n > 1 else 0
            se = st.sem(vals) if n > 1 else 0
            if n >= 2 and std > 0:
                ci = st.t.interval(CONFIDENCE_LEVEL, df=n-1, loc=mean, scale=se)
                margin = ci[1] - mean
            else:
                margin = 0
            cv = (std / mean * 100) if mean != 0 else 0

            stats_out[m] = {"mean": mean, "ci": margin, "std": std, "min": np.min(vals), "max": np.max(vals)}

            print(f"   {m:<18} | {np.min(vals):>8.1f} | {np.max(vals):>8.1f} | "
                  f"{mean:>8.1f} | {std:>8.1f} | {margin:>8.1f} | {cv:>5.1f}%")

        # Valores individuais (para identificar outliers)
        print(f"\n   Valores individuais (downtime, sla_viol, migrations):")
        for d in sorted(data, key=lambda x: x["downtime"]):
            flag = ""
            if d["downtime"] < 0 or d["sla_violations"] < 0:
                flag = " ⚠️ VALOR NEGATIVO!"
            print(f"      Run {d['run_id']}: DT={d['downtime']:>6.0f}  SLA={d['sla_violations']:>6.0f}  "
                  f"Mig={d['migrations']:>5.0f}  Delay={d['avg_delay']:>5.1f}  "
                  f"P={d['precision']:>5.1f}%  R={d['recall']:>5.1f}%{flag}")

    # ── 4. Verificação cruzada com valores no paper ──
    print(f"\n\n{'='*100}")
    print(f"VERIFICAÇÃO CRUZADA COM TABELA DO PAPER")
    print(f"{'='*100}")

    paper_values = {
        "K8s-Enhanced": {"downtime": 1505, "sla": 26110, "mig": 1910, "delay": 38.3},
        "K8s-Baseline": {"downtime": 2584, "sla": 26604, "mig": 220, "delay": 37.6},
        "TE-Tradeoff":  {"downtime": 1091, "sla": 1673,  "mig": 271, "delay": 16.6},
        "TE-Worst":     {"downtime": 930,  "sla": 2941,  "mig": 1876, "delay": 18.2},
        "TE-Best":      {"downtime": 856,  "sla": 2022,  "mig": 5471, "delay": 17.6},
    }

    print(f"\n{'Scenario':<15} | {'Metric':<10} | {'Paper':>8} | {'Computed':>8} | {'Diff':>8} | {'Match':>5}")
    print(f"{'-'*70}")

    for scenario in ["K8s-Enhanced", "K8s-Baseline", "TE-Tradeoff", "TE-Worst", "TE-Best"]:
        data = all_data.get(scenario, [])
        if not data:
            print(f"{scenario:<15} | {'N/A':<10} | {'N/A':>8} | {'NO DATA':>8} | {'N/A':>8} | {'❌':>5}")
            continue

        pv = paper_values[scenario]
        dt_mean = np.mean([d["downtime"] for d in data])
        sla_mean = np.mean([d["sla_violations"] for d in data])
        mig_mean = np.mean([d["migrations"] for d in data])
        dl_mean = np.mean([d["avg_delay"] for d in data])

        for label, paper_val, computed in [
            ("downtime", pv["downtime"], dt_mean),
            ("sla_viol", pv["sla"], sla_mean),
            ("migrate",  pv["mig"], mig_mean),
            ("delay",    pv["delay"], dl_mean),
        ]:
            diff = computed - paper_val
            pct = abs(diff / paper_val * 100) if paper_val != 0 else 0
            match = "✅" if pct < 1.0 else ("⚠️" if pct < 5.0 else "❌")
            print(f"{scenario:<15} | {label:<10} | {paper_val:>8.1f} | {computed:>8.1f} | "
                  f"{diff:>+8.1f} | {match:>5} ({pct:.1f}%)")

    # ── 5. Análise de Pareto ──
    print(f"\n\n{'='*100}")
    print(f"ANÁLISE DE FRONTEIRA DE PARETO (Migrações × Downtime)")
    print(f"{'='*100}")

    points = {}
    for scenario in ["TE-Best", "TE-Tradeoff", "TE-Worst", "K8s-Baseline", "K8s-Enhanced"]:
        data = all_data.get(scenario, [])
        if not data:
            continue
        mig = np.mean([d["migrations"] for d in data])
        dt = np.mean([d["downtime"] for d in data])
        sla = np.mean([d["sla_violations"] for d in data])
        points[scenario] = {"migrations": mig, "downtime": dt, "sla_violations": sla}

    print(f"\n{'Scenario':<15} | {'Migrations':>10} | {'Downtime':>10} | {'SLA Viol':>10} | Pareto?")
    print(f"{'-'*70}")

    for s, p in sorted(points.items(), key=lambda x: x[1]["migrations"]):
        # Check if dominated: exists another point with BOTH lower migrations AND lower downtime
        dominated_by = []
        for s2, p2 in points.items():
            if s2 == s:
                continue
            if p2["migrations"] <= p["migrations"] and p2["downtime"] <= p["downtime"]:
                if p2["migrations"] < p["migrations"] or p2["downtime"] < p["downtime"]:
                    dominated_by.append(s2)

        is_pareto = "✅ Pareto" if not dominated_by else f"❌ Dominated by {', '.join(dominated_by)}"
        print(f"{s:<15} | {p['migrations']:>10.0f} | {p['downtime']:>10.0f} | {p['sla_violations']:>10.0f} | {is_pareto}")

    # ── 6. Trade-off Analysis: Qual é realmente "Best", "Tradeoff", "Worst"? ──
    print(f"\n\n{'='*100}")
    print(f"VERIFICAÇÃO DE NOMENCLATURA (Best/Tradeoff/Worst)")
    print(f"{'='*100}")

    te_scenarios = {s: p for s, p in points.items() if s.startswith("TE-")}

    print(f"\n   Por Downtime (menor = melhor):")
    for s, p in sorted(te_scenarios.items(), key=lambda x: x[1]["downtime"]):
        print(f"      {s:<15} → {p['downtime']:.0f}")

    print(f"\n   Por SLA Violations (menor = melhor):")
    for s, p in sorted(te_scenarios.items(), key=lambda x: x[1]["sla_violations"]):
        print(f"      {s:<15} → {p['sla_violations']:.0f}")

    print(f"\n   Por Migrações (menor = melhor, menos custo):")
    for s, p in sorted(te_scenarios.items(), key=lambda x: x[1]["migrations"]):
        print(f"      {s:<15} → {p['migrations']:.0f}")

    print(f"\n   Score composto (45% DT_norm + 45% SLA_norm + 10% Mig_norm, menor = melhor):")
    dt_vals = [p["downtime"] for p in te_scenarios.values()]
    sla_vals = [p["sla_violations"] for p in te_scenarios.values()]
    mig_vals = [p["migrations"] for p in te_scenarios.values()]

    dt_min, dt_max = min(dt_vals), max(dt_vals)
    sla_min, sla_max = min(sla_vals), max(sla_vals)
    mig_min, mig_max = min(mig_vals), max(mig_vals)

    for s, p in te_scenarios.items():
        dt_norm = (p["downtime"] - dt_min) / (dt_max - dt_min) if dt_max != dt_min else 0
        sla_norm = (p["sla_violations"] - sla_min) / (sla_max - sla_min) if sla_max != sla_min else 0
        mig_norm = (p["migrations"] - mig_min) / (mig_max - mig_min) if mig_max != mig_min else 0
        score = dt_norm * 0.45 + sla_norm * 0.45 + mig_norm * 0.10
        print(f"      {s:<15} → score={score:.3f}  (DT_n={dt_norm:.2f}, SLA_n={sla_norm:.2f}, Mig_n={mig_norm:.2f})")

    print(f"\n{'='*100}")
    print(f"FIM DO DIAGNÓSTICO")
    print(f"{'='*100}")

    # ── 7. Testes Estatísticos (Cohen's d e p-values) ──
    print(f"\n\n{'='*100}")
    print(f"TESTES ESTATÍSTICOS (para Tabela do paper)")
    print(f"{'='*100}")

    from scipy.stats import mannwhitneyu, shapiro, ttest_ind

    comparisons = [
        ("TE-Best", "K8s-Baseline"),
        ("TE-Best", "K8s-Enhanced"),
        ("TE-Tradeoff", "K8s-Baseline"),
        ("TE-Tradeoff", "K8s-Enhanced"),
        ("TE-Worst", "K8s-Baseline"),
        ("TE-Worst", "K8s-Enhanced"),
        ("TE-Best", "TE-Tradeoff"),
        ("TE-Best", "TE-Worst"),
        ("K8s-Baseline", "K8s-Enhanced"),
    ]

    def cohens_d(a, b):
        na, nb = len(a), len(b)
        var_a, var_b = np.var(a, ddof=1), np.var(b, ddof=1)
        pooled_std = np.sqrt(((na - 1) * var_a + (nb - 1) * var_b) / (na + nb - 2))
        if pooled_std == 0:
            return 0.0
        return abs(np.mean(a) - np.mean(b)) / pooled_std

    print(f"\n{'Comparison':<30} | {'Metric':<12} | {'p-value':>10} | {'Cohen d':>8} | {'Test':>12}")
    print(f"{'-'*85}")

    for s1, s2 in comparisons:
        d1 = all_data.get(s1, [])
        d2 = all_data.get(s2, [])
        if not d1 or not d2:
            continue

        for metric in ["downtime", "sla_violations"]:
            a = np.array([d[metric] for d in d1])
            b = np.array([d[metric] for d in d2])

            # Shapiro-Wilk para normalidade
            _, p_a = shapiro(a)
            _, p_b = shapiro(b)

            if p_a > 0.05 and p_b > 0.05:
                _, p_val = ttest_ind(a, b, equal_var=False)
                test_name = "t-test"
            else:
                _, p_val = mannwhitneyu(a, b, alternative='two-sided')
                test_name = "Mann-Whitney"

            d = cohens_d(a, b)
            p_str = f"{p_val:.2e}" if p_val < 0.001 else f"{p_val:.4f}"
            print(f"{s1+' vs '+s2:<30} | {metric:<12} | {p_str:>10} | {d:>8.1f} | {test_name:>12}")

    # ── LaTeX output ──
    print(f"\n% LaTeX table for statistical tests:")
    for s1, s2 in comparisons:
        d1 = all_data.get(s1, [])
        d2 = all_data.get(s2, [])
        if not d1 or not d2:
            continue

        dt_a = np.array([d["downtime"] for d in d1])
        dt_b = np.array([d["downtime"] for d in d2])
        sla_a = np.array([d["sla_violations"] for d in d1])
        sla_b = np.array([d["sla_violations"] for d in d2])

        _, p_dt = mannwhitneyu(dt_a, dt_b, alternative='two-sided')
        _, p_sla = mannwhitneyu(sla_a, sla_b, alternative='two-sided')
        d_dt = cohens_d(dt_a, dt_b)
        d_sla = cohens_d(sla_a, sla_b)

        label = f"{s1} vs {s2}".replace("K8s-Baseline", "K8s-Base.").replace("K8s-Enhanced", "K8s-Enh.")
        p_dt_str = "${<}0{,}001$" if p_dt < 0.001 else f"${p_dt:.3f}$"
        p_sla_str = "${<}0{,}001$" if p_sla < 0.001 else f"${p_sla:.3f}$"
        print(f"{label} & {p_dt_str} & {d_dt:.1f} & {p_sla_str} & {d_sla:.1f} \\\\")


if __name__ == "__main__":
    main()