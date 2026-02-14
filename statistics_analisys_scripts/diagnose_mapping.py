"""
DIAGNÓSTICO DEFINITIVO: Verifica o mapeamento prefixo→cenário
lendo os parâmetros DENTRO de cada JSON.

Configurações esperadas (do analise_sensibilidade_trustedge.py):
  TE-Best:     w=30,  θ=50%,  h=300
  TE-Tradeoff: w=100, θ=60%,  h=100
  TE-Worst:    w=100, θ=75%,  h=200
"""
import json
import glob
import os
import re
import numpy as np
import scipy.stats as st

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")

# Configurações esperadas de cada cenário TrustEdge
EXPECTED_CONFIGS = {
    "TE-Best":     {"window_size": 30,  "reliability_threshold": 50.0, "lookahead": 300},
    "TE-Tradeoff": {"window_size": 100, "reliability_threshold": 60.0, "lookahead": 100},
    "TE-Worst":    {"window_size": 100, "reliability_threshold": 75.0, "lookahead": 200},
}

CONFIDENCE_LEVEL = 0.95


def ci95(arr):
    n = len(arr)
    if n < 2:
        return 0.0
    se = st.sem(arr)
    ci = st.t.interval(CONFIDENCE_LEVEL, df=n - 1, loc=np.mean(arr), scale=se)
    return ci[1] - np.mean(arr)


def main():
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "metrics_run_*.json")))
    print(f"Total files in results/: {len(files)}")

    # ── Grupo 1: Analisar por prefixo ──
    by_prefix = {}
    for f in files:
        match = re.search(r'metrics_run_(\d+)\.json', os.path.basename(f))
        if not match:
            continue
        run_id = match.group(1)
        prefix = run_id[:3]
        by_prefix.setdefault(prefix, []).append(f)

    print(f"\nPrefixos encontrados:")
    for prefix in sorted(by_prefix.keys()):
        print(f"   {prefix}: {len(by_prefix[prefix])} arquivos")

    # ── Grupo 2: Ler parâmetros dos prefixos 991-995 ──
    print(f"\n{'='*120}")
    print(f"ANÁLISE DETALHADA DOS PREFIXOS 991-995")
    print(f"{'='*120}")

    for prefix in ["991", "992", "993", "994", "995"]:
        file_list = by_prefix.get(prefix, [])
        if not file_list:
            print(f"\n⚠️  Prefixo {prefix}: SEM ARQUIVOS")
            continue

        print(f"\n{'─'*120}")
        print(f"PREFIXO {prefix} ({len(file_list)} arquivos)")
        print(f"{'─'*120}")

        # Ler primeiro arquivo para ver parâmetros
        params_found = set()
        all_metrics = []

        for f in sorted(file_list):
            try:
                with open(f) as fh:
                    content = json.load(fh)

                run_id = re.search(r'metrics_run_(\d+)\.json', os.path.basename(f)).group(1)

                # Extrair parâmetros (podem estar em diferentes locais)
                params = content.get("parameters", {})
                algo_params = content.get("algorithm_parameters", {})
                config = content.get("configuration", {})

                w = params.get("window_size",
                    algo_params.get("window_size",
                    config.get("window_size", "N/A")))

                rt = params.get("reliability_threshold",
                     algo_params.get("reliability_threshold",
                     config.get("reliability_threshold", "N/A")))

                h = params.get("lookahead",
                    algo_params.get("lookahead",
                    config.get("lookahead", "N/A")))

                algo = params.get("algorithm",
                       algo_params.get("algorithm",
                       config.get("algorithm",
                       content.get("algorithm", "N/A"))))

                params_found.add((w, rt, h, algo))

                # Métricas
                sla = content.get("sla", {})
                prov = content.get("provisioning_and_migration", {})
                pred = content.get("prediction_quality", {})

                m = {
                    "run_id": run_id,
                    "downtime": sla.get("total_perceived_downtime", -1),
                    "sla_violations": sla.get("total_delay_sla_violations", -1),
                    "migrations": prov.get("total_migrations", -1),
                    "avg_delay": sla.get("avg_delay", -1),
                    "precision": pred.get("precision", -1),
                    "recall": pred.get("recall", -1),
                    "w": w, "rt": rt, "h": h, "algo": algo,
                }
                all_metrics.append(m)
            except Exception as e:
                print(f"   ❌ Error {os.path.basename(f)}: {e}")

        # Mostrar parâmetros encontrados
        print(f"\n   Parâmetros encontrados:")
        for (w, rt, h, algo) in params_found:
            print(f"      window_size={w}, reliability_threshold={rt}, lookahead={h}, algorithm={algo}")

            # Tentar identificar qual cenário este é
            matched = None
            for name, expected in EXPECTED_CONFIGS.items():
                try:
                    if (float(w) == expected["window_size"] and
                        float(rt) == expected["reliability_threshold"]):
                        matched = name
                        break
                except (ValueError, TypeError):
                    pass
            if matched:
                print(f"      → CORRESPONDE A: {matched}")
            else:
                print(f"      → NÃO CORRESPONDE a nenhuma config TrustEdge conhecida (K8s?)")

        # Mostrar chaves de nível superior do JSON (para entender estrutura)
        sample = json.load(open(sorted(file_list)[0]))
        print(f"\n   Chaves do JSON (nível superior): {sorted(sample.keys())}")
        if "parameters" in sample:
            print(f"   content['parameters']: {sample['parameters']}")
        if "algorithm_parameters" in sample:
            print(f"   content['algorithm_parameters']: {sample['algorithm_parameters']}")
        if "configuration" in sample:
            print(f"   content['configuration']: {sample['configuration']}")

        # Estatísticas
        if all_metrics:
            arr_dt   = np.array([m["downtime"]       for m in all_metrics])
            arr_sla  = np.array([m["sla_violations"]  for m in all_metrics])
            arr_mig  = np.array([m["migrations"]      for m in all_metrics])
            arr_dl   = np.array([m["avg_delay"]       for m in all_metrics])
            arr_prec = np.array([m["precision"]        for m in all_metrics])
            arr_rec  = np.array([m["recall"]           for m in all_metrics])

            print(f"\n   Métricas (n={len(all_metrics)}):")
            print(f"   {'Metric':<18} | {'Mean':>10} | {'±CI95':>8} | {'Min':>8} | {'Max':>8} | {'Std':>8}")
            print(f"   {'-'*70}")
            for name, arr in [("downtime", arr_dt), ("sla_violations", arr_sla),
                              ("migrations", arr_mig), ("avg_delay", arr_dl),
                              ("precision", arr_prec), ("recall", arr_rec)]:
                mean = np.mean(arr)
                margin = ci95(arr)
                print(f"   {name:<18} | {mean:>10.1f} | {margin:>8.1f} | {np.min(arr):>8.1f} | {np.max(arr):>8.1f} | {np.std(arr, ddof=1):>8.1f}")

    # ── Grupo 3: Comparação com valores do paper ──
    print(f"\n\n{'='*120}")
    print(f"COMPARAÇÃO COM VALORES NA TABELA DO PAPER")
    print(f"{'='*120}")

    paper_table = {
        "K8s-Enhanced":  {"prefix": "995", "downtime": 4804, "sla": 27267, "mig": 1894, "delay": 38.3},
        "K8s-Baseline":  {"prefix": "994", "downtime": 2584, "sla": 26604, "mig": 220,  "delay": 37.6},
        "TE-Tradeoff":   {"prefix": "993", "downtime": 1091, "sla": 1673,  "mig": 271,  "delay": 16.6},
        "TE-Worst":      {"prefix": "992", "downtime": 930,  "sla": 2941,  "mig": 1876, "delay": 18.2},
        "TE-Best":       {"prefix": "991", "downtime": 856,  "sla": 2022,  "mig": 5471, "delay": 17.6},
    }

    print(f"\n{'Scenario':<15} | {'Prefix':>6} | {'Metric':<12} | {'Paper':>8} | {'Real':>8} | {'Diff':>8} | {'Status'}")
    print(f"{'-'*90}")

    for scenario, info in paper_table.items():
        prefix = info["prefix"]
        file_list = by_prefix.get(prefix, [])
        if not file_list:
            print(f"{scenario:<15} | {prefix:>6} | {'ALL':<12} | {'':>8} | {'NO DATA':>8} | {'':>8} | ❌")
            continue

        metrics = []
        for f in file_list:
            try:
                with open(f) as fh:
                    c = json.load(fh)
                metrics.append({
                    "downtime": c["sla"]["total_perceived_downtime"],
                    "sla":      c["sla"]["total_delay_sla_violations"],
                    "mig":      c["provisioning_and_migration"]["total_migrations"],
                    "delay":    c["sla"].get("avg_delay", -1),
                })
            except Exception:
                pass

        for metric_name in ["downtime", "sla", "mig", "delay"]:
            paper_val = info[metric_name]
            real_val = np.mean([m[metric_name] for m in metrics])
            diff = real_val - paper_val
            pct = abs(diff / paper_val * 100) if paper_val != 0 else 0
            status = "✅" if pct < 1.0 else ("⚠️" if pct < 5.0 else "❌ MISMATCH")
            print(f"{scenario:<15} | {prefix:>6} | {metric_name:<12} | {paper_val:>8.1f} | {real_val:>8.1f} | {diff:>+8.1f} | {status} ({pct:.1f}%)")

    # ── Grupo 4: Análise de dominância Pareto ──
    print(f"\n\n{'='*120}")
    print(f"ANÁLISE DE DOMINÂNCIA DE PARETO (Migrações × Downtime)")
    print(f"{'='*120}")

    # Usar dados REAIS dos JSONs
    real_means = {}
    for scenario, info in paper_table.items():
        prefix = info["prefix"]
        file_list = by_prefix.get(prefix, [])
        metrics = []
        for f in file_list:
            try:
                with open(f) as fh:
                    c = json.load(fh)
                metrics.append({
                    "downtime": c["sla"]["total_perceived_downtime"],
                    "mig":      c["provisioning_and_migration"]["total_migrations"],
                    "sla":      c["sla"]["total_delay_sla_violations"],
                })
            except Exception:
                pass
        if metrics:
            real_means[scenario] = {
                "migrations": np.mean([m["mig"] for m in metrics]),
                "downtime":   np.mean([m["downtime"] for m in metrics]),
                "sla":        np.mean([m["sla"] for m in metrics]),
            }

    print(f"\n{'Scenario':<15} | {'Migrations':>10} | {'Downtime':>10} | {'SLA Viol':>10} | Pareto (Mig×DT)?")
    print(f"{'-'*80}")

    for s in sorted(real_means.keys(), key=lambda x: real_means[x]["migrations"]):
        p = real_means[s]
        dominated_by = []
        for s2, p2 in real_means.items():
            if s2 == s:
                continue
            if p2["migrations"] <= p["migrations"] and p2["downtime"] <= p["downtime"]:
                if p2["migrations"] < p["migrations"] or p2["downtime"] < p["downtime"]:
                    dominated_by.append(s2)
        status = "✅ PARETO" if not dominated_by else f"❌ Dominado por: {', '.join(dominated_by)}"
        print(f"{s:<15} | {p['migrations']:>10.0f} | {p['downtime']:>10.0f} | {p['sla']:>10.0f} | {status}")

    # Pareto 3D (Mig × DT × SLA)
    print(f"\n{'Scenario':<15} | Pareto 3D (Mig×DT×SLA)?")
    print(f"{'-'*60}")
    for s in sorted(real_means.keys(), key=lambda x: real_means[x]["migrations"]):
        p = real_means[s]
        dominated_by = []
        for s2, p2 in real_means.items():
            if s2 == s:
                continue
            if (p2["migrations"] <= p["migrations"] and
                p2["downtime"] <= p["downtime"] and
                p2["sla"] <= p["sla"]):
                if (p2["migrations"] < p["migrations"] or
                    p2["downtime"] < p["downtime"] or
                    p2["sla"] < p["sla"]):
                    dominated_by.append(s2)
        status = "✅ PARETO-3D" if not dominated_by else f"❌ Dominado por: {', '.join(dominated_by)}"
        print(f"{s:<15} | {status}")


if __name__ == "__main__":
    main()