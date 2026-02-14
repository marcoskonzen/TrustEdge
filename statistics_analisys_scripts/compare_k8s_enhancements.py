"""
Comparação de Kubernetes Standard com Enhancements
===================================================

Executa 6 simulações EM PARALELO (otimizado para MacBook Air M1):
1. Kubernetes Baseline (registry-only + cold migration + reactive)
2. Kubernetes + P2P (P2P + cold migration + reactive)
3. Kubernetes + Live Migration (registry-only + live migration + reactive)
4. Kubernetes + P2P + Live (P2P + live migration + reactive)
5. Kubernetes + Proactive SLA (registry-only + cold migration + proactive)
6. Kubernetes + TUDO (P2P + live migration + proactive SLA) ← TESTE COMPLETO!

Gera relatório comparativo completo.
"""

import subprocess
import json
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import platform
import psutil

# ============================================================================
# DETECÇÃO DE HARDWARE
# ============================================================================

def detect_hardware():
    """Detecta hardware e retorna número ótimo de workers paralelos."""
    cpu_count = psutil.cpu_count(logical=False)  # Cores físicos
    is_m1 = platform.processor() == 'arm' and platform.system() == 'Darwin'
    
    # M1 tem 8 cores (4 performance + 4 efficiency)
    # Para simulações pesadas, usar no máximo 4 workers em paralelo
    max_workers = min(4, cpu_count) if is_m1 else min(2, cpu_count)
    
    print(f"\n{'='*70}")
    print(f"HARDWARE DETECTADO")
    print(f"{'='*70}")
    print(f"  Sistema: {platform.system()} {platform.machine()}")
    print(f"  Processador: {platform.processor()}")
    print(f"  Cores físicos: {cpu_count}")
    print(f"  M1 Mac: {'SIM ✅' if is_m1 else 'NÃO'}")
    print(f"  Workers paralelos: {max_workers}")
    print(f"{'='*70}\n")
    
    return max_workers, is_m1

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

CONFIGURATIONS = [
    # ──────────────────────────────────────────────────────────
    # BASELINE
    # ──────────────────────────────────────────────────────────
    {
        "name": "Baseline",
        "enable_p2p": False,
        "enable_live_migration": False,
        "enable_proactive_sla_migration": False
    },
    
    # ──────────────────────────────────────────────────────────
    # FEATURES ISOLADAS (Single Enhancement)
    # ──────────────────────────────────────────────────────────
    {
        "name": "P2P Only",
        "enable_p2p": True,
        "enable_live_migration": False,
        "enable_proactive_sla_migration": False
    },
    {
        "name": "Live Only",
        "enable_p2p": False,
        "enable_live_migration": True,
        "enable_proactive_sla_migration": False
    },
    {
        "name": "Proactive SLA Only",
        "enable_p2p": False,
        "enable_live_migration": False,
        "enable_proactive_sla_migration": True
    },
    
    # ──────────────────────────────────────────────────────────
    # COMBINAÇÕES DE 2 FEATURES
    # ──────────────────────────────────────────────────────────
    {
        "name": "P2P + Live",
        "enable_p2p": True,
        "enable_live_migration": True,
        "enable_proactive_sla_migration": False
    },
    {
        "name": "P2P + Proactive SLA",  # ✅ NOVO!
        "enable_p2p": True,
        "enable_live_migration": False,
        "enable_proactive_sla_migration": True
    },
    {
        "name": "Live + Proactive SLA",  # ✅ NOVO!
        "enable_p2p": False,
        "enable_live_migration": True,
        "enable_proactive_sla_migration": True
    },
    
    # ──────────────────────────────────────────────────────────
    # FULL STACK (All Enhancements)
    # ──────────────────────────────────────────────────────────
    {
        "name": "Full Stack (P2P + Live + SLA)",
        "enable_p2p": True,
        "enable_live_migration": True,
        "enable_proactive_sla_migration": True
    },
]

SIMULATION_PARAMS = {
    "algorithm": "kubernetes_inspired",
    "seed": 11108889,
    "time_steps": 1500,
    "dataset": "datasets/dataset_extended.json",
}

# ============================================================================
# EXECUTAR SIMULAÇÃO INDIVIDUAL
# ============================================================================

def run_simulation(config, sim_params, config_index, total_configs):
    """
    Executa uma única configuração de simulação.
    
    Args:
        config (dict): Configuração (nome + flags)
        sim_params (dict): Parâmetros globais da simulação
        config_index (int): Índice da configuração (1-based)
        total_configs (int): Total de configurações
    
    Returns:
        tuple: (success, config_name, elapsed_time)
    """
    name = config["name"]
    
    # ✅ Construir comando
    cmd = [
        "python", "-m", "simulator",
        "--algorithm", sim_params["algorithm"],
        "--seed", str(sim_params["seed"]),
        "--time-steps", str(sim_params["time_steps"]),
        "--input", sim_params["dataset"]
    ]
    
    # ✅ Adicionar flags de enhancements
    flags_passed = []
    
    if config.get("enable_p2p"):
        cmd.append("--enable-p2p")
        flags_passed.append("--enable-p2p")
    
    if config.get("enable_live_migration"):
        cmd.append("--enable-live-migration")
        flags_passed.append("--enable-live-migration")
    
    if config.get("enable_proactive_sla_migration"):
        cmd.append("--enable-proactive-sla-migration")
        flags_passed.append("--enable-proactive-sla-migration")
    
    # ✅ Print informações
    print(f"\n[{config_index}/{total_configs}] 🚀 INICIANDO: {name}")
    print(f"        P2P: {'ON ✅' if config.get('enable_p2p') else 'OFF ❌'}")
    print(f"        Live Migration: {'ON ✅' if config.get('enable_live_migration') else 'OFF ❌'}")
    print(f"        Proactive SLA: {'ON ✅' if config.get('enable_proactive_sla_migration') else 'OFF ❌'}")
    print(f"        Comando: {' '.join(cmd)}")
    print(f"        Flags CLI: {', '.join(flags_passed) if flags_passed else 'NENHUMA ❌'}\n")
    
    start_time = time.time()
    
    try:
        # ✅ Executar com timeout de 1 hora
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=3600,
            env=os.environ.copy()
        )
        
        elapsed_time = time.time() - start_time
        
        if result.returncode != 0:
            print(f"[{config_index}/{total_configs}] ❌ ERRO: {name}")
            print(f"        Tempo decorrido: {elapsed_time/60:.1f} min")
            print(f"        Stderr (últimas 500 chars):")
            print(f"        {result.stderr[-500:]}")
            return (False, name, elapsed_time)
        
        print(f"[{config_index}/{total_configs}] ✅ CONCLUÍDO: {name}")
        print(f"        Tempo decorrido: {elapsed_time/60:.1f} min\n")
        return (True, name, elapsed_time)
        
    except subprocess.TimeoutExpired:
        elapsed_time = time.time() - start_time
        print(f"[{config_index}/{total_configs}] ⏱️ TIMEOUT: {name}")
        print(f"        Tempo decorrido: {elapsed_time/60:.1f} min (excedeu 60 min)\n")
        return (False, name, elapsed_time)
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"[{config_index}/{total_configs}] ❌ EXCEÇÃO: {name}")
        print(f"        Erro: {e}")
        print(f"        Tempo decorrido: {elapsed_time/60:.1f} min\n")
        return (False, name, elapsed_time)

# ============================================================================
# EXECUTAR TODAS AS SIMULAÇÕES EM PARALELO
# ============================================================================

def run_all_simulations_parallel(max_workers):
    """
    Executa todas as configurações EM PARALELO.
    
    Args:
        max_workers: Número máximo de processos paralelos
    
    Returns:
        list: Lista de resultados carregados dos arquivos JSON
    """
    
    total_configs = len(CONFIGURATIONS)
    
    print(f"\n{'#'*70}")
    print(f"# EXECUTANDO {total_configs} SIMULAÇÕES EM PARALELO")
    print(f"# Workers: {max_workers} | Timeout: 60 min/simulação")
    print(f"{'#'*70}\n")
    
    overall_start = time.time()
    results_data = []
    execution_summary = []
    
    # ✅ Executar em paralelo usando ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submeter todas as tarefas
        future_to_config = {
            executor.submit(run_simulation, config, SIMULATION_PARAMS, i+1, total_configs): (config, i+1)
            for i, config in enumerate(CONFIGURATIONS)
        }
        
        # Coletar resultados conforme completam
        for future in as_completed(future_to_config):
            config, config_index = future_to_config[future]
            
            try:
                success, config_name, elapsed_time = future.result()
                execution_summary.append({
                    'config_name': config_name,
                    'success': success,
                    'elapsed_time': elapsed_time
                })
                
                if success:
                    # ✅ Carregar arquivo JSON correspondente
                    config_suffix = get_config_suffix(config)
                    filename = f"results/k8s{config_suffix}_results.json"
                    
                    try:
                        with open(filename, 'r') as f:
                            data = json.load(f)
                            data['config_name'] = config_name
                            results_data.append(data)
                    except FileNotFoundError:
                        print(f"⚠️ [{config_index}/{total_configs}] Arquivo não encontrado: {filename}")
                        
            except Exception as e:
                print(f"❌ [{config_index}/{total_configs}] Exceção ao processar resultado: {e}")
    
    overall_elapsed = time.time() - overall_start
    
    # ✅ Imprimir resumo de execução
    print(f"\n{'='*70}")
    print(f"RESUMO DA EXECUÇÃO PARALELA")
    print(f"{'='*70}")
    print(f"  Tempo total: {overall_elapsed/60:.1f} min ({overall_elapsed:.1f} s)")
    print(f"  Simulações bem-sucedidas: {sum(1 for s in execution_summary if s['success'])}/{total_configs}")
    print(f"\n  Detalhamento:")
    
    for summary in execution_summary:
        status = "✅ Sucesso" if summary['success'] else "❌ Falha"
        print(f"    {summary['config_name']:30s} | {status} | {summary['elapsed_time']/60:.1f} min")
    
    print(f"{'='*70}\n")
    
    return results_data

def get_config_suffix(config):
    """Retorna sufixo do arquivo JSON baseado na configuração."""
    p2p = config["enable_p2p"]
    live = config["enable_live_migration"]
    sla = config["enable_proactive_sla_migration"]
    
    if p2p and live and sla:
        return "_p2p_live_sla"
    elif p2p and live:
        return "_p2p_live"
    elif p2p and sla:
        return "_p2p_sla"
    elif live and sla:
        return "_live_sla"
    elif p2p:
        return "_p2p"
    elif live:
        return "_live"
    elif sla:
        return "_sla"
    else:
        return "_baseline"

# ============================================================================
# GERAR RELATÓRIO COMPARATIVO
# ============================================================================

def generate_comparative_report(results):
    """Gera relatório comparativo em texto e gráficos."""
    
    if not results:
        print("❌ Nenhum resultado para comparar!")
        return
    
    # 1. Criar DataFrame COMPLETO
    df = pd.DataFrame([
    {
        'Configuration': r['config_name'],
        'P2P': r['configuration']['enable_p2p'],
        'Live': r['configuration']['enable_live_migration'],
        'Proactive SLA': r['configuration'].get('enable_proactive_sla_migration', False),
        
        # ✅ Métricas principais
        'Downtime (steps)': r['sla']['total_perceived_downtime'],
        'SLA Violations': r['sla']['total_delay_sla_violations'],
        
        # ✅ Migrações
        'Total Migrations': r['provisioning_and_migration']['total_migrations'],
        'Successful': r['provisioning_and_migration']['migrations_finished'],
        'Failed': r['provisioning_and_migration']['migrations_interrupted'],
        'Success Rate (%)': round(
            (r['provisioning_and_migration']['migrations_finished'] / 
             r['provisioning_and_migration']['total_migrations'] * 100) 
            if r['provisioning_and_migration']['total_migrations'] > 0 else 0, 
            1
        ),
        
        # ✅ CORREÇÃO: Ler chaves corretas
        'Reactive (server_failed)': r['provisioning_and_migration'].get('migrations_by_reason', {}).get('server_failed', 0),
        'Proactive (delay_violation)': r['provisioning_and_migration'].get('migrations_by_reason', {}).get('delay_violation', 0),
        
        # ✅ NOVO: Breakdown de server_failed (opcional)
        'Cold Migrations': r['provisioning_and_migration'].get('server_failed_breakdown', {}).get('cold_migrations', 0),
        'Hot Migrations': r['provisioning_and_migration'].get('server_failed_breakdown', {}).get('hot_migrations', 0),
        
        'Avg Migration Time': round(r['provisioning_and_migration'].get('avg_migration_time', 0), 3),
        
        'Latency Samples': r['total_latency_samples'],
        'Avg Latency (ms)': round(r['sla'].get('avg_delay', 0), 2),
    }
    for r in results
])
    
    # 2. Relatório em Texto (MELHORADO)
    print("\n" + "="*100)
    print("RELATÓRIO COMPARATIVO - KUBERNETES ENHANCEMENTS")
    print("="*100 + "\n")
    
    # ✅ Tabela principal (métricas chave)
    main_cols = ['Configuration', 'P2P', 'Live', 'Proactive SLA', 
                 'Downtime (steps)', 'SLA Violations', 
                 'Total Migrations', 'Success Rate (%)', 'Avg Latency (ms)']
    print(df[main_cols].to_string(index=False))
    
    # ✅ Tabela de breakdown de migrações (se disponível)
    if 'Reactive (server_failed)' in df.columns:
        print("\n" + "-"*100)
        print("BREAKDOWN DE MIGRAÇÕES")
        print("-"*100 + "\n")
        
        migration_cols = ['Configuration', 'Total Migrations', 
                        'Reactive (server_failed)', 'Proactive (delay_violation)', 
                        'Successful', 'Failed']
        print(df[migration_cols].to_string(index=False))
        
        # ✅ VALIDAÇÃO: Total = Reactive + Proactive
        print("\n" + "-"*100)
        print("VALIDAÇÃO: Total Migrations = Reactive + Proactive")
        print("-"*100 + "\n")
        
        for _, row in df.iterrows():
            total = row['Total Migrations']
            reactive = row['Reactive (server_failed)']
            proactive = row['Proactive (delay_violation)']
            computed_total = reactive + proactive
            
            status = "✅" if total == computed_total else "❌"
            difference = total - computed_total
            
            print(f"{status} {row['Configuration']:30s} | Total: {total:4d} | Reactive: {reactive:4d} | Proactive: {proactive:4d} | Sum: {computed_total:4d} | Diff: {difference:+4d}")
    
    # 3. Calcular melhorias relativas ao Baseline
    baseline_rows = df[df['Configuration'] == 'Baseline']
    
    if len(baseline_rows) > 0:
        baseline = baseline_rows.iloc[0]
        
        print(f"\n{'='*100}")
        print("MELHORIAS RELATIVAS AO BASELINE")
        print("="*100 + "\n")
        
        for _, row in df[df['Configuration'] != 'Baseline'].iterrows():
            print(f"{row['Configuration']}:")
            
            # ✅ Downtime
            if baseline['Downtime (steps)'] > 0:
                downtime_improvement = ((baseline['Downtime (steps)'] - row['Downtime (steps)']) / baseline['Downtime (steps)']) * 100
            else:
                downtime_improvement = 0
            
            # ✅ SLA Violations
            if baseline['SLA Violations'] > 0:
                sla_improvement = ((baseline['SLA Violations'] - row['SLA Violations']) / baseline['SLA Violations']) * 100
            else:
                sla_improvement = 0
            
            # ✅ Latency
            if baseline['Avg Latency (ms)'] > 0:
                latency_improvement = ((baseline['Avg Latency (ms)'] - row['Avg Latency (ms)']) / baseline['Avg Latency (ms)']) * 100
            else:
                latency_improvement = 0
            
            # ✅ Success Rate
            success_rate_diff = row['Success Rate (%)'] - baseline['Success Rate (%)']
            
            print(f"  ├─ Downtime: {downtime_improvement:+.1f}% ({'✅ melhoria' if downtime_improvement > 0 else '❌ piora'})")
            print(f"  ├─ SLA Violations: {sla_improvement:+.1f}% ({'✅ melhoria' if sla_improvement > 0 else '❌ piora'})")
            print(f"  ├─ Avg Latency: {latency_improvement:+.1f}% ({'✅ melhoria' if latency_improvement > 0 else '❌ piora'})")
            print(f"  └─ Success Rate: {success_rate_diff:+.1f}pp ({'✅ melhoria' if success_rate_diff > 0 else '❌ piora'})")
            print()
    else:
        print(f"\n⚠️ Baseline não encontrado - não é possível calcular melhorias relativas")
    
    # 4. Salvar CSV
    os.makedirs('results', exist_ok=True)
    df.to_csv('results/k8s_comparison.csv', index=False)
    print(f"✅ CSV salvo: results/k8s_comparison.csv\n")
    
    # 5. Gerar Gráficos
    generate_comparison_charts(df, results)

def generate_comparison_charts(df, results):
    """Gera gráficos comparativos."""
    
    sns.set_style("whitegrid")
    
    # ✅ Paleta de cores para 8 configurações
    colors = [
        '#FF6B6B',  # 1. Baseline
        '#4ECDC4',  # 2. P2P Only
        '#45B7D1',  # 3. Live Only
        '#96CEB4',  # 4. Proactive SLA Only
        '#FFA07A',  # 5. P2P + Live
        '#98D8C8',  # 6. P2P + Proactive SLA
        '#DDA15E',  # 7. Live + Proactive SLA
        '#BC6C25',  # 8. Full Stack
    ]
    
    # ✅ Fallback para mais de 8 configurações
    if len(df) > len(colors):
        colors = sns.color_palette("husl", len(df))
    
    # ═══════════════════════════════════════════════════════════════════════
    # GRÁFICO 1: Comparação de Métricas Principais (Barras)
    # ═══════════════════════════════════════════════════════════════════════
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(18, 11))  # ✅ Aumentar tamanho
    
    # Downtime
    ax1.bar(range(len(df)), df['Downtime (steps)'], color=colors[:len(df)])
    ax1.set_ylabel('Downtime (steps)', fontsize=11)
    ax1.set_title('Total Downtime Comparison', fontsize=12, fontweight='bold')
    ax1.set_xticks(range(len(df)))
    ax1.set_xticklabels(df['Configuration'], rotation=45, ha='right', fontsize=8)  # ✅ Reduzir fonte
    ax1.grid(axis='y', alpha=0.3)
    
    # SLA Violations
    ax2.bar(range(len(df)), df['SLA Violations'], color=colors[:len(df)])
    ax2.set_ylabel('SLA Violations', fontsize=11)
    ax2.set_title('SLA Violations Comparison', fontsize=12, fontweight='bold')
    ax2.set_xticks(range(len(df)))
    ax2.set_xticklabels(df['Configuration'], rotation=45, ha='right', fontsize=8)
    ax2.grid(axis='y', alpha=0.3)
    
    # Total Migrations
    ax3.bar(range(len(df)), df['Total Migrations'], color=colors[:len(df)])
    ax3.set_ylabel('Total Migrations', fontsize=11)
    ax3.set_title('Total Migrations Comparison', fontsize=12, fontweight='bold')
    ax3.set_xticks(range(len(df)))
    ax3.set_xticklabels(df['Configuration'], rotation=45, ha='right', fontsize=8)
    ax3.grid(axis='y', alpha=0.3)
    
    # Success Rate
    ax4.bar(range(len(df)), df['Success Rate (%)'], color=colors[:len(df)])
    ax4.set_ylabel('Success Rate (%)', fontsize=11)
    ax4.set_title('Migration Success Rate Comparison', fontsize=12, fontweight='bold')
    ax4.set_xticks(range(len(df)))
    ax4.set_xticklabels(df['Configuration'], rotation=45, ha='right', fontsize=8)
    ax4.set_ylim([90, 100])
    ax4.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('results/k8s_comparison_bars.pdf')
    plt.savefig('results/k8s_comparison_bars.png', dpi=300)
    plt.close()
    
    print(f"✅ Gráficos de barras salvos: results/k8s_comparison_bars.{{pdf,png}}\n")
    
    # ═══════════════════════════════════════════════════════════════════════
    # GRÁFICO 2: CDF de Latências
    # ═══════════════════════════════════════════════════════════════════════
    fig, ax = plt.subplots(figsize=(14, 8))  # ✅ Aumentar tamanho
    
    for i, r in enumerate(results):
        latencies = sorted(r['raw_latencies'])
        cdf = [j/len(latencies) for j in range(1, len(latencies)+1)]
        
        # ✅ Garantir que índice existe
        color = colors[i] if i < len(colors) else colors[i % len(colors)]
        
        ax.plot(latencies, cdf, label=r['config_name'], linewidth=2.5, color=color)
    
    ax.set_xlabel('Latency (ms)', fontsize=12)
    ax.set_ylabel('CDF', fontsize=12)
    ax.set_title('Latency CDF Comparison', fontsize=14, fontweight='bold')
    ax.legend(fontsize=9, loc='lower right')  # ✅ Reduzir fonte da legenda
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('results/k8s_latency_cdf.pdf')
    plt.savefig('results/k8s_latency_cdf.png', dpi=300)
    plt.close()
    
    print(f"✅ CDF salvo: results/k8s_latency_cdf.{{pdf,png}}\n")
    
    # ═══════════════════════════════════════════════════════════════════════
    # GRÁFICO 3: Breakdown de Migrações (Stacked Bar) - SE DISPONÍVEL
    # ═══════════════════════════════════════════════════════════════════════
    if 'Reactive (server_failed)' in df.columns and 'Proactive (delay_violation)' in df.columns:
        fig, ax = plt.subplots(figsize=(14, 7))  # ✅ Aumentar largura
        
        x = range(len(df))
        reactive = df['Reactive (server_failed)']
        proactive = df['Proactive (delay_violation)']
        
        ax.bar(x, reactive, label='Reactive (server_failed)', color='#FF6B6B')
        ax.bar(x, proactive, bottom=reactive, label='Proactive (delay_violation)', color='#4ECDC4')
        
        ax.set_ylabel('Number of Migrations', fontsize=12)
        ax.set_title('Migration Type Breakdown', fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(df['Configuration'], rotation=45, ha='right', fontsize=9)  # ✅ Reduzir fonte
        ax.legend(fontsize=11)
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('results/k8s_migration_breakdown.pdf')
        plt.savefig('results/k8s_migration_breakdown.png', dpi=300)
        plt.close()
        
        print(f"✅ Breakdown de migrações salvo: results/k8s_migration_breakdown.{{pdf,png}}\n")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Detectar hardware
    max_workers, is_m1 = detect_hardware()
    
    total_configs = len(CONFIGURATIONS)
    
    print(f"\n{'#'*70}")
    print(f"# COMPARAÇÃO DE KUBERNETES ENHANCEMENTS")
    print(f"# {total_configs} Configurações × {SIMULATION_PARAMS['time_steps']} steps")
    print(f"# Execução: PARALELA ({max_workers} workers)")
    print(f"{'#'*70}\n")
    
    overall_start = time.time()
    
    # ✅ Executar simulações em paralelo
    results = run_all_simulations_parallel(max_workers)
    
    overall_elapsed = time.time() - overall_start
    
    # Gerar relatório
    if results:
        generate_comparative_report(results)
        
        print(f"\n{'='*70}")
        print(f"✅ COMPARAÇÃO CONCLUÍDA!")
        print(f"   Tempo total: {overall_elapsed/60:.1f} min ({overall_elapsed:.1f} s)")
        print(f"   Simulações bem-sucedidas: {len(results)}/{total_configs}")
        print(f"   Resultados: results/k8s_comparison.csv")
        print(f"   Gráficos: results/k8s_comparison_*.{{pdf,png}}")
        print(f"{'='*70}\n")
    else:
        print(f"\n{'='*70}")
        print(f"❌ NENHUMA SIMULAÇÃO FOI CONCLUÍDA COM SUCESSO!")
        print(f"   Tempo total: {overall_elapsed/60:.1f} min")
        print(f"{'='*70}\n")