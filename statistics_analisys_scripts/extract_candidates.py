import pandas as pd
import os
import glob
import sys

# Config
# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Go up one level to find the project root
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
# Build the correct absolute path to the results
RESULTS_DIR = os.path.join(PROJECT_ROOT, 'sensitivity_analysis_results')

def get_latest_results():
    # Find the latest CSV
    print(f"Searching for results in: {RESULTS_DIR}")
    files = glob.glob(os.path.join(RESULTS_DIR, 'sensitivity_results_*.csv'))
    if not files:
        raise FileNotFoundError(f"No sensitivity results found in {RESULTS_DIR}")
    
    latest_file = max(files, key=os.path.getctime)
    print(f"Loading data from: {os.path.basename(latest_file)}") # Clean print
    return pd.read_csv(latest_file)

def select_candidates():
    # ...existing code...
    df = get_latest_results()
    
    # Ensure we are looking at averages across repetitions if they exist
    cols = ['window_size', 'reliability_threshold', 'lookahead']
    # Filter only relevant metrics
    metrics = ['perceived_downtime', 'sla_violations', 'total_migrations', 'f1_score']
    
    # Group by configuration to get the mean of repetitions
    df_avg = df.groupby(cols)[metrics].mean().reset_index()

    # =========================================================================
    # CÁLCULO DE SCORE DE QUALIDADE DE SERVIÇO (QoS)
    # Baseado EXCLUSIVAMENTE em Downtime e Violações de SLA
    # =========================================================================
    
    # 1. Normalização (0 a 1) para que as escalas diferentes não enviesem a soma
    max_dt = df_avg['perceived_downtime'].max()
    max_sla = df_avg['sla_violations'].max()
    
    # Safety check for zero max to avoid division by zero
    max_dt = max_dt if max_dt > 0 else 1.0
    max_sla = max_sla if max_sla > 0 else 1.0

    df_avg['norm_downtime'] = df_avg['perceived_downtime'] / max_dt
    df_avg['norm_sla'] = df_avg['sla_violations'] / max_sla
    
    # 2. Combined Score (Lower is Better)
    # Score 0.0 = Melhor QoS possível
    # Score 1.0 = Pior QoS possível
    df_avg['qos_penalty_score'] = (df_avg['norm_downtime'] + df_avg['norm_sla']) / 2.0
    
    # Ordenar do melhor (menor score) para o pior (maior score)
    df_sorted = df_avg.sort_values(by='qos_penalty_score')

    # -------------------------------------------------------------------------
    # SELEÇÃO DOS CANDIDATOS
    # -------------------------------------------------------------------------

    # 1. BEST SOLUTION (Menor penalidade combinada)
    best = df_sorted.iloc[0]
    
    # 2. WORST SOLUTION (Maior penalidade combinada)
    worst = df_sorted.iloc[-1]
    
    # 3. TRADE-OFF / REPRESENTATIVE SOLUTION (Mediana)
    # Seleciona a configuração que está extamente no meio da distribuição.
    # Isso representa o "caso médio" ou trade-off natural entre as métricas extremas.
    median_idx = len(df_sorted) // 2
    tradeoff = df_sorted.iloc[median_idx]

    candidates = {
        "BEST": best,
        "WORST": worst,
        "TRADEOFF": tradeoff
    }

    print("\n=== SELECTED CONFIGURATIONS FOR STATISTICAL VALIDATION (n=30) ===")
    print(f"Criteria: Combined Normalized Score of Downtime + SLA Violations")
    print("-" * 75)
    
    for name, data in candidates.items():
        print(f"\n[{name}] Score: {data['qos_penalty_score']:.4f}")
        print(f"  Window: {int(data['window_size'])}")
        print(f"  Threshold: {int(data['reliability_threshold'])}")
        print(f"  Lookahead: {int(data['lookahead'])}")
        print(f"  -----------------------------")
        print(f"  Est. Downtime: {data['perceived_downtime']:.2f}")
        print(f"  Est. SLA Viol: {data['sla_violations']:.2f}")
        print(f"  (Migrations):  {data['total_migrations']:.1f}")
    
    return candidates

if __name__ == "__main__":
    select_candidates()