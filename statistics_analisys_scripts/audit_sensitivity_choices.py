"""
AUDITORIA COMPLETA da análise de sensibilidade — V3 ROBUSTA.
Auto-detecta arquivos CSV e colunas. Corrige mapeamento e match por lookahead.
"""
import csv
import glob
import os
import sys
import numpy as np
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SENSITIVITY_DIR = os.path.join(PROJECT_ROOT, "sensitivity_analysis_results")

# Configurações declaradas no paper e no run_validation_experiments.py
DECLARED_CONFIGS = {
    "TE-Best":     {"window_size": 30,  "reliability_threshold": 50.0, "lookahead": 300},
    "TE-Tradeoff": {"window_size": 100, "reliability_threshold": 60.0, "lookahead": 100},
    "TE-Worst":    {"window_size": 100, "reliability_threshold": 75.0, "lookahead": 200},
}


def find_file(directory, pattern, description):
    """Encontra arquivo por glob pattern, lista alternativas se falhar."""
    matches = sorted(glob.glob(os.path.join(directory, pattern)))
    if matches:
        chosen = matches[-1]  # mais recente
        print(f"   ✅ {description}: {os.path.basename(chosen)}")
        if len(matches) > 1:
            print(f"      (Outros encontrados: {[os.path.basename(m) for m in matches[:-1]]})")
        return chosen
    # Listar tudo que existe no diretório
    if os.path.isdir(directory):
        all_files = sorted(os.listdir(directory))
        print(f"   ❌ {description}: nenhum arquivo com pattern '{pattern}'")
        print(f"      Arquivos disponíveis em {os.path.basename(directory)}/:")
        for f in all_files:
            print(f"         {f}")
    else:
        print(f"   ❌ Diretório não encontrado: {directory}")
    return None


def load_csv(filepath):
    if not filepath or not os.path.exists(filepath):
        print(f"   ❌ File not found: {filepath}")
        return [], []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        rows = list(reader)
    print(f"   ✅ Loaded {len(rows)} rows, {len(cols)} columns from {os.path.basename(filepath)}")
    return rows, cols


def sf(val, default=0.0):
    """Safe float conversion."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def detect_column(columns, candidates, description):
    """Detecta a coluna correta a partir de uma lista de candidatos."""
    for candidate in candidates:
        if candidate in columns:
            return candidate
    # Tentar match parcial
    for candidate in candidates:
        for col in columns:
            if candidate.lower() in col.lower():
                print(f"      ⚠️  {description}: match parcial '{col}' (buscando '{candidate}')")
                return col
    return None


def print_column_summary(rows, cols):
    """Imprime resumo de todas as colunas com tipos e ranges."""
    print(f"\n   Todas as colunas ({len(cols)}):")
    print(f"   {'#':<3} | {'Coluna':<40} | {'Min':>12} | {'Max':>12} | {'Sample[0]':>15} | Tipo")
    print(f"   {'-'*100}")
    for i, c in enumerate(cols):
        vals = [sf(r[c], None) for r in rows]
        numeric_vals = [v for v in vals if v is not None]
        sample = rows[0][c] if rows else "?"
        
        if numeric_vals and len(numeric_vals) == len(vals):
            vmin, vmax = min(numeric_vals), max(numeric_vals)
            dtype = "float" if any('.' in str(rows[j][c]) for j in range(min(3, len(rows)))) else "int"
            print(f"   {i:<3} | {c:<40} | {vmin:>12.2f} | {vmax:>12.2f} | {sample:>15} | {dtype}")
        else:
            print(f"   {i:<3} | {c:<40} | {'N/A':>12} | {'N/A':>12} | {str(sample)[:15]:>15} | text")


def main():
    print("=" * 120)
    print("AUDITORIA DA ANÁLISE DE SENSIBILIDADE — V3 ROBUSTA")
    print("=" * 120)

    # ════════════════════════════════════════════════════════════
    # PARTE 0: Encontrar arquivos
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 0: LOCALIZAÇÃO DE ARQUIVOS")
    print(f"{'─'*120}")
    print(f"\n   Diretório: {SENSITIVITY_DIR}")

    results_file = find_file(SENSITIVITY_DIR, "sensitivity_results_*.csv", "Resultados brutos")
    ranking_file = find_file(SENSITIVITY_DIR, "configuration_ranking*.csv", "Ranking")
    
    if not results_file:
        # Tentar qualquer CSV
        results_file = find_file(SENSITIVITY_DIR, "*.csv", "Qualquer CSV")
        if not results_file:
            print("\n   ❌ Nenhum arquivo CSV encontrado. Abortando.")
            return

    # ════════════════════════════════════════════════════════════
    # PARTE 1: Carregar e inspecionar dados brutos
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 1: INSPEÇÃO DOS DADOS BRUTOS")
    print(f"{'─'*120}")

    raw_data, raw_cols = load_csv(results_file)
    if not raw_data:
        return

    print_column_summary(raw_data, raw_cols)

    # ════════════════════════════════════════════════════════════
    # PARTE 1b: Auto-detectar colunas
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 1b: AUTO-DETECÇÃO DE COLUNAS")
    print(f"{'─'*120}")

    COL_WINDOW = detect_column(raw_cols, 
        ["window_size", "param_window", "w"], "Window size")
    COL_THRESHOLD = detect_column(raw_cols, 
        ["reliability_threshold", "param_threshold", "threshold", "rt"], "Threshold")
    COL_LOOKAHEAD = detect_column(raw_cols, 
        ["lookahead", "param_lookahead", "h", "look_ahead"], "Lookahead")
    COL_DOWNTIME = detect_column(raw_cols, 
        ["perceived_downtime", "downtime", "total_downtime", "avg_downtime"], "Downtime")
    COL_SLA = detect_column(raw_cols, 
        ["sla_violations", "sla_violation", "total_sla_violations"], "SLA Violations")
    COL_MIGRATIONS = detect_column(raw_cols, 
        ["total_migrations", "migrations", "num_migrations", "migration_count"], "Migrations")

    required = {
        "Window": COL_WINDOW, "Threshold": COL_THRESHOLD, "Lookahead": COL_LOOKAHEAD,
        "Downtime": COL_DOWNTIME, "SLA": COL_SLA, "Migrations": COL_MIGRATIONS
    }

    print(f"\n   Mapeamento detectado:")
    all_found = True
    for desc, col in required.items():
        if col:
            # Mostrar range de valores para confirmar
            vals = [sf(r[col]) for r in raw_data]
            print(f"      {desc:<12} → '{col}' (range: [{min(vals):.1f}, {max(vals):.1f}])")
        else:
            print(f"      {desc:<12} → ❌ NÃO ENCONTRADA")
            all_found = False

    if not all_found:
        print(f"\n   ❌ Colunas essenciais não encontradas. Verifique os nomes acima.")
        return

    # Verificar se downtime tem valores razoáveis (não é uma coluna de contagem pequena)
    dt_vals_check = [sf(r[COL_DOWNTIME]) for r in raw_data]
    dt_max_check = max(dt_vals_check)
    if dt_max_check < 50:
        print(f"\n   ⚠️  ATENÇÃO: Coluna de downtime '{COL_DOWNTIME}' tem max={dt_max_check:.1f}")
        print(f"      Isso parece uma contagem/interseção, NÃO tempo de downtime real!")
        print(f"      Candidatas alternativas com valores maiores:")
        for c in raw_cols:
            vals = [sf(r[c]) for r in raw_data]
            vmax = max(vals)
            if vmax > 100 and "time" in c.lower() or "downtime" in c.lower() or "down" in c.lower():
                print(f"         '{c}' (range: [{min(vals):.1f}, {vmax:.1f}])")

    # ════════════════════════════════════════════════════════════
    # PARTE 2: Agrupar por configuração
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 2: AGRUPAMENTO POR CONFIGURAÇÃO (w, θ, h)")
    print(f"{'─'*120}")

    configs = defaultdict(list)
    for row in raw_data:
        w = sf(row[COL_WINDOW])
        rt = sf(row[COL_THRESHOLD])
        h = sf(row[COL_LOOKAHEAD])
        configs[(w, rt, h)].append(row)

    print(f"\n   Configurações únicas: {len(configs)}")
    runs_per = [len(v) for v in configs.values()]
    print(f"   Runs por configuração: min={min(runs_per)}, max={max(runs_per)}, "
          f"média={np.mean(runs_per):.1f}, total={sum(runs_per)}")

    # Listar valores únicos de cada parâmetro
    ws = sorted(set(k[0] for k in configs.keys()))
    rts = sorted(set(k[1] for k in configs.keys()))
    hs = sorted(set(k[2] for k in configs.keys()))
    print(f"   Window sizes:  {ws}")
    print(f"   Thresholds:    {rts}")
    print(f"   Lookaheads:    {hs}")
    print(f"   Grid total:    {len(ws)} × {len(rts)} × {len(hs)} = {len(ws)*len(rts)*len(hs)}")

    # ════════════════════════════════════════════════════════════
    # PARTE 3: Calcular estatísticas por configuração
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 3: MÉTRICAS POR CONFIGURAÇÃO")
    print(f"{'─'*120}")

    config_stats = []
    for (w, rt, h), rows in sorted(configs.items()):
        dt_vals = np.array([sf(r[COL_DOWNTIME]) for r in rows])
        sla_vals = np.array([sf(r[COL_SLA]) for r in rows])
        mig_vals = np.array([sf(r[COL_MIGRATIONS]) for r in rows])

        config_stats.append({
            "w": w, "rt": rt, "h": h,
            "n": len(rows),
            "dt_mean": np.mean(dt_vals),
            "dt_std": np.std(dt_vals, ddof=1) if len(dt_vals) > 1 else 0,
            "sla_mean": np.mean(sla_vals),
            "sla_std": np.std(sla_vals, ddof=1) if len(sla_vals) > 1 else 0,
            "mig_mean": np.mean(mig_vals),
            "mig_std": np.std(mig_vals, ddof=1) if len(mig_vals) > 1 else 0,
        })

    # ════════════════════════════════════════════════════════════
    # PARTE 4: Normalizar e calcular scores
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 4: NORMALIZAÇÃO E SCORES")
    print(f"{'─'*120}")

    dt_means = np.array([c["dt_mean"] for c in config_stats])
    sla_means = np.array([c["sla_mean"] for c in config_stats])
    mig_means = np.array([c["mig_mean"] for c in config_stats])

    dt_min, dt_max = dt_means.min(), dt_means.max()
    sla_min, sla_max = sla_means.min(), sla_means.max()
    mig_min, mig_max = mig_means.min(), mig_means.max()

    print(f"\n   Ranges das médias:")
    print(f"      Downtime:   [{dt_min:.1f}, {dt_max:.1f}]  (Δ = {dt_max-dt_min:.1f})")
    print(f"      SLA Viol.:  [{sla_min:.1f}, {sla_max:.1f}]  (Δ = {sla_max-sla_min:.1f})")
    print(f"      Migrations: [{mig_min:.1f}, {mig_max:.1f}]  (Δ = {mig_max-mig_min:.1f})")

    for c in config_stats:
        c["dt_norm"] = (c["dt_mean"] - dt_min) / (dt_max - dt_min) if dt_max != dt_min else 0
        c["sla_norm"] = (c["sla_mean"] - sla_min) / (sla_max - sla_min) if sla_max != sla_min else 0
        c["mig_norm"] = (c["mig_mean"] - mig_min) / (mig_max - mig_min) if mig_max != mig_min else 0

        c["score_50_50"] = c["dt_norm"] * 0.5 + c["sla_norm"] * 0.5
        c["score_45_45_10"] = c["dt_norm"] * 0.45 + c["sla_norm"] * 0.45 + c["mig_norm"] * 0.10
        c["score_dt_only"] = c["dt_norm"]
        c["score_sla_only"] = c["sla_norm"]

    # ════════════════════════════════════════════════════════════
    # PARTE 5: Rankings completos
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 5: RANKINGS (top 10 + bottom 10 de cada fórmula)")
    print(f"{'─'*120}")

    for score_name, desc in [
        ("score_50_50", "50% Downtime + 50% SLA"),
        ("score_45_45_10", "45% DT + 45% SLA + 10% Mig"),
        ("score_dt_only", "100% Downtime"),
    ]:
        sorted_configs = sorted(config_stats, key=lambda c: c[score_name])
        total = len(sorted_configs)

        print(f"\n   ┌─ {desc} ('{score_name}') ─ menor = melhor")
        print(f"   │ {'#':<4} | {'w':>4} | {'θ':>5} | {'h':>5} | {'Score':>8} | "
              f"{'DT_mean':>10} | {'SLA_mean':>10} | {'Mig_mean':>10} | Match")
        print(f"   │ {'-'*100}")

        show_indices = list(range(min(10, total))) + list(range(max(total-10, 10), total))
        prev_i = -1
        for i in show_indices:
            if i <= prev_i:
                continue
            if prev_i >= 0 and i - prev_i > 1:
                print(f"   │ {'...':^4} |")
            prev_i = i

            c = sorted_configs[i]
            rank = i + 1
            marker = ""
            for name, expected in DECLARED_CONFIGS.items():
                if (c["w"] == expected["window_size"] and
                    c["rt"] == expected["reliability_threshold"] and
                    c["h"] == expected["lookahead"]):
                    marker = f" ← ★ {name}"

            print(f"   │ {rank:<4} | {c['w']:>4.0f} | {c['rt']:>5.1f} | {c['h']:>5.0f} | "
                  f"{c[score_name]:>8.4f} | {c['dt_mean']:>10.1f} | {c['sla_mean']:>10.1f} | "
                  f"{c['mig_mean']:>10.1f}{marker}")
        print(f"   └─")

    # ════════════════════════════════════════════════════════════
    # PARTE 6: Verificação exata das escolhas declaradas
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 6: VERIFICAÇÃO DAS ESCOLHAS DECLARADAS (match exato w, θ, h)")
    print(f"{'─'*120}")

    sorted_50_50 = sorted(config_stats, key=lambda c: c["score_50_50"])
    best_config = sorted_50_50[0]
    worst_config = sorted_50_50[-1]
    total = len(sorted_50_50)

    print(f"\n   Usando score_50_50 (0.5·DT_norm + 0.5·SLA_norm):")
    print(f"   Rank 1 (BEST):     w={best_config['w']:.0f}, θ={best_config['rt']:.1f}, "
          f"h={best_config['h']:.0f} | score={best_config['score_50_50']:.4f} | "
          f"DT={best_config['dt_mean']:.1f}, SLA={best_config['sla_mean']:.1f}, "
          f"Mig={best_config['mig_mean']:.1f}")
    print(f"   Rank {total} (WORST):  w={worst_config['w']:.0f}, θ={worst_config['rt']:.1f}, "
          f"h={worst_config['h']:.0f} | score={worst_config['score_50_50']:.4f} | "
          f"DT={worst_config['dt_mean']:.1f}, SLA={worst_config['sla_mean']:.1f}, "
          f"Mig={worst_config['mig_mean']:.1f}")

    for name, expected in DECLARED_CONFIGS.items():
        found = None
        for c in config_stats:
            if (c["w"] == expected["window_size"] and
                c["rt"] == expected["reliability_threshold"] and
                c["h"] == expected["lookahead"]):
                found = c
                break

        print(f"\n   {name} (w={expected['window_size']}, θ={expected['reliability_threshold']}, "
              f"h={expected['lookahead']}):")

        if found:
            rank = sorted_50_50.index(found) + 1
            pct = rank / total * 100

            print(f"      Rank score_50_50:  {rank}/{total} (percentil {pct:.0f}%)")
            print(f"      DT={found['dt_mean']:.1f} (±{found['dt_std']:.1f}), "
                  f"SLA={found['sla_mean']:.1f} (±{found['sla_std']:.1f}), "
                  f"Mig={found['mig_mean']:.1f} (±{found['mig_std']:.1f})")
            print(f"      Normalized: DT={found['dt_norm']:.4f}, SLA={found['sla_norm']:.4f}, "
                  f"Mig={found['mig_norm']:.4f}")
            print(f"      Score: {found['score_50_50']:.4f}")

            if name == "TE-Best":
                if rank == 1:
                    print(f"      ✅ CONFIRMADO como rank 1 (melhor configuração)")
                else:
                    print(f"      ⚠️  NÃO é rank 1! É rank {rank}.")
                    print(f"      → Rank 1 real: w={best_config['w']:.0f}, "
                          f"θ={best_config['rt']:.1f}, h={best_config['h']:.0f}")
                    # Mostrar diferença
                    print(f"         DT: {best_config['dt_mean']:.1f} vs {found['dt_mean']:.1f} "
                          f"(Δ={found['dt_mean']-best_config['dt_mean']:.1f})")
                    print(f"         SLA: {best_config['sla_mean']:.1f} vs {found['sla_mean']:.1f} "
                          f"(Δ={found['sla_mean']-best_config['sla_mean']:.1f})")

            elif name == "TE-Worst":
                if rank == total:
                    print(f"      ✅ CONFIRMADO como rank {total} (pior configuração)")
                elif rank >= total - 5:
                    print(f"      ⚠️  Não é o último, mas está no bottom 5 (rank {rank}/{total})")
                    print(f"      → Rank {total} real: w={worst_config['w']:.0f}, "
                          f"θ={worst_config['rt']:.1f}, h={worst_config['h']:.0f}")
                else:
                    print(f"      ❌ PROBLEMA: rank {rank}/{total} — nem perto do pior!")
                    print(f"      → Rank {total} real: w={worst_config['w']:.0f}, "
                          f"θ={worst_config['rt']:.1f}, h={worst_config['h']:.0f}")

            elif name == "TE-Tradeoff":
                # Verificar se tem bom score MAS com poucas migrações
                mig_rank = sorted(range(len(config_stats)),
                                  key=lambda i: config_stats[i]["mig_mean"]).index(
                    config_stats.index(found)) + 1
                print(f"      Rank de migrações: {mig_rank}/{total} (1=menos migrações)")
                if rank <= total // 3 and found['mig_mean'] < np.median(mig_means):
                    print(f"      ✅ Bom tradeoff: top 33% em score, abaixo da mediana em migrações")
                else:
                    print(f"      ⚠️  Avaliar se é realmente um bom tradeoff")
        else:
            print(f"      ❌ NÃO ENCONTRADA no grid!")
            partial = [c for c in config_stats
                       if c["w"] == expected["window_size"]
                       and c["rt"] == expected["reliability_threshold"]]
            if partial:
                print(f"      Matches parciais (w={expected['window_size']}, "
                      f"θ={expected['reliability_threshold']}):")
                for p in sorted(partial, key=lambda x: x["h"]):
                    r = sorted_50_50.index(p) + 1
                    print(f"         h={p['h']:.0f}: rank={r}/{total}, "
                          f"DT={p['dt_mean']:.1f}, SLA={p['sla_mean']:.1f}, "
                          f"Mig={p['mig_mean']:.1f}")

    # ════════════════════════════════════════════════════════════
    # PARTE 7: Comparação com configuration_ranking.csv
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 7: COMPARAÇÃO COM configuration_ranking.csv")
    print(f"{'─'*120}")

    if ranking_file:
        ranking_data, ranking_cols = load_csv(ranking_file)
        if ranking_data:
            print(f"\n   Colunas do ranking: {ranking_cols}")
            print_column_summary(ranking_data, ranking_cols)

            # Reverse engineer the composite score formula
            print(f"\n   Reverse engineering do composite_score:")
            all_match = True
            detected_formula = None

            for idx, r in enumerate(ranking_data[:10]):
                dn = sf(r.get("downtime_norm", r.get("dt_norm", 0)))
                sn = sf(r.get("sla_norm", 0))
                mn = sf(r.get("mig_norm", r.get("migration_norm", 0)))
                cs = sf(r.get("composite_score", r.get("score", 0)))

                if idx == 0:
                    print(f"\n      Norm columns found: downtime_norm={'downtime_norm' in ranking_cols}, "
                          f"sla_norm={'sla_norm' in ranking_cols}, "
                          f"mig_norm={'mig_norm' in ranking_cols}")

                # Brute-force with step 0.05
                best_err = 999
                best_formula = None
                for a_pct in range(0, 105, 5):
                    for b_pct in range(0, 105 - a_pct, 5):
                        c_pct = 100 - a_pct - b_pct
                        a, b, c_w = a_pct / 100, b_pct / 100, c_pct / 100
                        test = dn * a + sn * b + mn * c_w
                        err = abs(test - cs)
                        if err < best_err:
                            best_err = err
                            best_formula = (a, b, c_w, test)

                if best_formula and best_err < 0.001:
                    a, b, c_w, test = best_formula
                    w = r.get(COL_WINDOW, r.get("window_size", "?"))
                    rt = r.get(COL_THRESHOLD, r.get("reliability_threshold", "?"))
                    h = r.get(COL_LOOKAHEAD, r.get("lookahead", "?"))
                    if idx < 3:
                        print(f"      [{idx}] w={w}, θ={rt}, h={h}: "
                              f"{a:.2f}·DT + {b:.2f}·SLA + {c_w:.2f}·Mig = {test:.6f} "
                              f"(cs={cs:.6f}, err={best_err:.2e})")
                    if detected_formula is None:
                        detected_formula = (a, b, c_w)
                    elif (a, b, c_w) != detected_formula:
                        all_match = False
                else:
                    all_match = False
                    if idx < 3:
                        print(f"      [{idx}] ❌ No formula match (best err={best_err:.4f})")

            if detected_formula and all_match:
                a, b, c_w = detected_formula
                print(f"\n      🎯 FÓRMULA CONSISTENTE DETECTADA:")
                print(f"         composite_score = {a:.2f}·downtime_norm + {b:.2f}·sla_norm + "
                      f"{c_w:.2f}·mig_norm")
            elif detected_formula:
                print(f"\n      ⚠️  Fórmula candidata {detected_formula} mas não consistente em todas as linhas")

            # Ranking top/bottom
            cs_col = "composite_score" if "composite_score" in ranking_cols else "score"
            ranked = sorted(ranking_data, key=lambda r: sf(r.get(cs_col, 99)))

            # Encontrar colunas de parâmetros no ranking
            rk_w = detect_column(ranking_cols, ["window_size", "param_window"], "RK window")
            rk_rt = detect_column(ranking_cols, ["reliability_threshold", "param_threshold"], "RK threshold")
            rk_h = detect_column(ranking_cols, ["lookahead", "param_lookahead"], "RK lookahead")

            print(f"\n   Top 5 do ranking.csv:")
            for i, r in enumerate(ranked[:5]):
                w = r.get(rk_w, "?") if rk_w else "?"
                rt = r.get(rk_rt, "?") if rk_rt else "?"
                h = r.get(rk_h, "?") if rk_h else "?"
                cs = sf(r.get(cs_col, 0))
                print(f"      [{i+1}] w={w}, θ={rt}, h={h} → score={cs:.4f}")

            print(f"\n   Bottom 5 do ranking.csv:")
            for i, r in enumerate(ranked[-5:]):
                w = r.get(rk_w, "?") if rk_w else "?"
                rt = r.get(rk_rt, "?") if rk_rt else "?"
                h = r.get(rk_h, "?") if rk_h else "?"
                cs = sf(r.get(cs_col, 0))
                print(f"      [{len(ranked)-4+i}] w={w}, θ={rt}, h={h} → score={cs:.4f}")

            # Match configurações declaradas
            print(f"\n   Configurações declaradas no ranking.csv:")
            for name, expected in DECLARED_CONFIGS.items():
                for r in ranked:
                    w = sf(r.get(rk_w, 0)) if rk_w else -1
                    rt = sf(r.get(rk_rt, 0)) if rk_rt else -1
                    h = sf(r.get(rk_h, 0)) if rk_h else -1
                    if (w == expected["window_size"] and
                        rt == expected["reliability_threshold"] and
                        h == expected["lookahead"]):
                        idx = ranked.index(r) + 1
                        cs = sf(r.get(cs_col, 0))
                        print(f"      {name}: rank={idx}/{len(ranked)}, score={cs:.4f}")
                        break
                else:
                    print(f"      {name}: ❌ NÃO ENCONTRADO (verificar nomes de colunas)")

    # ════════════════════════════════════════════════════════════
    # PARTE 8: Fronteira de Pareto (DT × Mig)
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 8: FRONTEIRA DE PARETO (Downtime × Migrações)")
    print(f"{'─'*120}")

    pareto = []
    for c in config_stats:
        dominated = False
        for c2 in config_stats:
            if c is c2:
                continue
            if (c2["dt_mean"] <= c["dt_mean"] and c2["mig_mean"] <= c["mig_mean"] and
                (c2["dt_mean"] < c["dt_mean"] or c2["mig_mean"] < c["mig_mean"])):
                dominated = True
                break
        if not dominated:
            pareto.append(c)

    pareto_sorted = sorted(pareto, key=lambda c: c["mig_mean"])
    print(f"\n   Fronteira de Pareto ({len(pareto)}/{len(config_stats)} configurações):")
    print(f"   {'w':>4} | {'θ':>5} | {'h':>5} | {'DT_mean':>10} | {'SLA_mean':>10} | "
          f"{'Mig_mean':>10} | {'Score_50':>8} | Match")
    print(f"   {'-'*90}")
    for c in pareto_sorted:
        marker = ""
        for name, expected in DECLARED_CONFIGS.items():
            if (c["w"] == expected["window_size"] and
                c["rt"] == expected["reliability_threshold"] and
                c["h"] == expected["lookahead"]):
                marker = f" ← ★ {name}"
        rank = sorted_50_50.index(c) + 1
        print(f"   {c['w']:>4.0f} | {c['rt']:>5.1f} | {c['h']:>5.0f} | "
              f"{c['dt_mean']:>10.1f} | {c['sla_mean']:>10.1f} | "
              f"{c['mig_mean']:>10.1f} | {c['score_50_50']:>8.4f} | rank {rank}{marker}")

    # ════════════════════════════════════════════════════════════
    # PARTE 9: Correlação entre parâmetros e métricas
    # ════════════════════════════════════════════════════════════
    print(f"\n{'─'*120}")
    print("PARTE 9: CORRELAÇÃO PARÂMETROS → MÉTRICAS")
    print(f"{'─'*120}")

    param_arrays = {
        "window_size": np.array([c["w"] for c in config_stats]),
        "threshold": np.array([c["rt"] for c in config_stats]),
        "lookahead": np.array([c["h"] for c in config_stats]),
    }
    metric_arrays = {
        "downtime": dt_means,
        "sla_violations": sla_means,
        "migrations": mig_means,
    }

    print(f"\n   Pearson correlation:")
    print(f"   {'':>15} | {'downtime':>12} | {'sla_viol':>12} | {'migrations':>12}")
    print(f"   {'-'*55}")
    for pname, pvals in param_arrays.items():
        corrs = []
        for mname, mvals in metric_arrays.items():
            r = np.corrcoef(pvals, mvals)[0, 1]
            corrs.append(r)
        print(f"   {pname:>15} | {corrs[0]:>12.3f} | {corrs[1]:>12.3f} | {corrs[2]:>12.3f}")

    # ════════════════════════════════════════════════════════════
    # PARTE 10: Resumo executivo
    # ════════════════════════════════════════════════════════════
    print(f"\n{'='*120}")
    print("RESUMO EXECUTIVO")
    print(f"{'='*120}")

    true_best = sorted_50_50[0]
    true_worst = sorted_50_50[-1]

    print(f"\n   RANK 1 (Melhor score 50/50):")
    print(f"      w={true_best['w']:.0f}, θ={true_best['rt']:.1f}, h={true_best['h']:.0f}")
    print(f"      DT={true_best['dt_mean']:.1f}, SLA={true_best['sla_mean']:.1f}, "
          f"Mig={true_best['mig_mean']:.1f}  |  Score={true_best['score_50_50']:.4f}")

    print(f"\n   RANK {total} (Pior score 50/50):")
    print(f"      w={true_worst['w']:.0f}, θ={true_worst['rt']:.1f}, h={true_worst['h']:.0f}")
    print(f"      DT={true_worst['dt_mean']:.1f}, SLA={true_worst['sla_mean']:.1f}, "
          f"Mig={true_worst['mig_mean']:.1f}  |  Score={true_worst['score_50_50']:.4f}")

    # Melhor tradeoff: na fronteira de Pareto, menor migrações com score razoável
    pareto_not_best = [c for c in pareto_sorted if c is not true_best]
    if pareto_not_best:
        true_tradeoff = min(pareto_not_best, key=lambda c: c["mig_mean"])
        r_t = sorted_50_50.index(true_tradeoff) + 1
        print(f"\n   MELHOR TRADEOFF (menor mig na fronteira de Pareto, excl. best):")
        print(f"      w={true_tradeoff['w']:.0f}, θ={true_tradeoff['rt']:.1f}, "
              f"h={true_tradeoff['h']:.0f}")
        print(f"      DT={true_tradeoff['dt_mean']:.1f}, SLA={true_tradeoff['sla_mean']:.1f}, "
              f"Mig={true_tradeoff['mig_mean']:.1f}  |  Score={true_tradeoff['score_50_50']:.4f} "
              f"(rank {r_t}/{total})")

    print(f"\n   CONFIGURAÇÕES DECLARADAS:")
    for name, expected in DECLARED_CONFIGS.items():
        found = None
        for c in config_stats:
            if (c["w"] == expected["window_size"] and
                c["rt"] == expected["reliability_threshold"] and
                c["h"] == expected["lookahead"]):
                found = c
                break
        if found:
            rank = sorted_50_50.index(found) + 1
            status = "✅" if (
                (name == "TE-Best" and rank <= 3) or
                (name == "TE-Worst" and rank >= total - 3) or
                (name == "TE-Tradeoff" and rank <= total // 2)
            ) else "⚠️"
            print(f"      {status} {name:<15}: rank {rank:>3}/{total}  |  "
                  f"DT={found['dt_mean']:>8.1f}  SLA={found['sla_mean']:>8.1f}  "
                  f"Mig={found['mig_mean']:>8.1f}  |  Score={found['score_50_50']:.4f}")
        else:
            print(f"      ❌ {name:<15}: NÃO ENCONTRADA no grid")

    # Verdito final
    print(f"\n   {'─'*80}")
    print(f"   VEREDICTO:")

    declared_best = None
    for c in config_stats:
        exp = DECLARED_CONFIGS["TE-Best"]
        if (c["w"] == exp["window_size"] and c["rt"] == exp["reliability_threshold"] and
            c["h"] == exp["lookahead"]):
            declared_best = c
            break

    if declared_best:
        rank_best = sorted_50_50.index(declared_best) + 1
        if rank_best == 1:
            print(f"   ✅ TE-Best está correto (rank 1).")
        elif rank_best <= 3:
            print(f"   ⚠️  TE-Best é rank {rank_best} (quase correto, diferença pode ser ruído).")
            print(f"      Considerar se o rank 1 é estatisticamente distinto.")
        else:
            print(f"   ❌ TE-Best é rank {rank_best}/{total} — PRECISA SER CORRIGIDO.")
            print(f"      → Sugestão para novo TE-Best: w={true_best['w']:.0f}, "
                  f"θ={true_best['rt']:.1f}, h={true_best['h']:.0f}")
    else:
        print(f"   ❌ TE-Best NÃO ENCONTRADA no grid — PRECISA SER CORRIGIDO.")

    print(f"\n{'='*120}")


if __name__ == "__main__":
    main()
