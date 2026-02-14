import subprocess
import os
import multiprocessing
import sys
import platform
import time
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.append(PROJECT_ROOT)

# Settings
REPETITIONS = 30
DATASET = os.path.join("datasets", "dataset_extended.json")
BASE_SEED = 5000
TIME_STEPS = 1500

IS_ARM_MAC = (platform.system() == 'Darwin' and platform.machine() == 'arm64')
MAX_WORKERS = max(1, multiprocessing.cpu_count() - 1)

# ═══════════════════════════════════════════════════════════════
# GRADE COMPLETA: 3 algoritmos × 3 configurações = 9 cenários
# ═══════════════════════════════════════════════════════════════
#
# Nomenclatura dos módulos:
#   FPM = Failure Prediction Module (M2)
#   LTM = Live Transfer Module (M3 P2P + M4 Live Migration)
#
# ╔══════════════════════════════════════════════════════════════╗
# ║ MAPEAMENTO DE IDs (ATUALIZADO para evitar conflitos)       ║
# ║                                                             ║
# ║ IDs antigos preservados:                                    ║
# ║   991 = TE-Best     (w=30, θ=50, h=300) → agora TE-FPM-LTM║
# ║   992 = TE-Worst    (w=100,θ=75, h=200) → PRESERVADO       ║
# ║   993 = TE-Tradeoff (w=100,θ=60, h=100) → PRESERVADO       ║
# ║   994 = K8s-Baseline                    → agora K8s-D       ║
# ║   995 = K8s-Enhanced                    → agora K8s-FPM-LTM ║
# ║                                                             ║
# ║ Novos IDs (sem conflito):                                   ║
# ║   101 = TE-D         (TrustEdge Default, sem M2/M3/M4)     ║
# ║   102 = TE-FPM       (TrustEdge + Predição, sem M3/M4)     ║
# ║   103 = K8s-FPM      (K8s + Predição, sem M3/M4)           ║
# ║   104 = FF-D         (First-Fit Default)                    ║
# ║   105 = FF-FPM       (First-Fit + Predição)                ║
# ║   106 = FF-FPM-LTM   (First-Fit + Predição + Live/P2P)    ║
# ╚══════════════════════════════════════════════════════════════╝

# ── TrustEdge Best params (from sensitivity analysis) ──
TE_BEST_PARAMS = {
    "window_size": 30,
    "reliability_threshold": 50,
    "lookahead": 300,
}

# ═══════════════════════════════════════════════════════════════
# CENÁRIOS JÁ EXISTENTES (NÃO re-executar por padrão)
# ═══════════════════════════════════════════════════════════════
EXISTING_SCENARIOS = {
    "TE-FPM-LTM": {
        "scenario_id": "991",
        "description": "TrustEdge com todos os módulos (M1+M2+M3+M4)",
        "has_results": True,
    },
    "K8s-D": {
        "scenario_id": "994",
        "description": "Kubernetes vanilla (reativo puro)",
        "has_results": True,
    },
    "K8s-FPM-LTM": {
        "scenario_id": "995",
        "description": "Kubernetes com todos os módulos",
        "has_results": True,
    },
}

# ═══════════════════════════════════════════════════════════════
# CENÁRIOS NOVOS (executar)
# ═══════════════════════════════════════════════════════════════

# ── TrustEdge ──
TRUSTEDGE_NEW_SCENARIOS = {
    # TrustEdge Default (apenas M1 — política de orquestração, sem predição/live/P2P)
    "TE-D": {
        "scenario_id": "101",
        "algorithm": "trust_edge_v3",
        "params": TE_BEST_PARAMS,
        "enable_p2p": False,
        "enable_live_migration": False,
        "enable_failure_prediction": False,
    },
    # TrustEdge com FPM mas SEM live/P2P
    "TE-FPM": {
        "scenario_id": "102",
        "algorithm": "trust_edge_v3",
        "params": TE_BEST_PARAMS,
        "enable_p2p": False,
        "enable_live_migration": False,
        "enable_failure_prediction": True,
    },
}

# ── Kubernetes ──
KUBERNETES_NEW_SCENARIOS = {
    # K8s com FPM mas SEM live/P2P
    "K8s-FPM": {
        "scenario_id": "103",
        "algorithm": "kubernetes_inspired",
        "enable_p2p": False,
        "enable_live_migration": False,
        "enable_proactive_sla_migration": False,
        "enable_failure_prediction": True,
    },
}

# ── First-Fit ──
FIRST_FIT_NEW_SCENARIOS = {
    # First-Fit Default (guloso, reativo puro)
    "FF-D": {
        "scenario_id": "104",
        "algorithm": "first_fit_baseline",
        "enable_p2p": False,
        "enable_live_migration": False,
        "enable_failure_prediction": False,
    },
    # First-Fit com FPM
    "FF-FPM": {
        "scenario_id": "105",
        "algorithm": "first_fit_baseline",
        "enable_p2p": False,
        "enable_live_migration": False,
        "enable_failure_prediction": True,
    },
    # First-Fit com FPM + LTM
    "FF-FPM-LTM": {
        "scenario_id": "106",
        "algorithm": "first_fit_baseline",
        "enable_p2p": True,
        "enable_live_migration": True,
        "enable_failure_prediction": True,
    },
}


# ═══════════════════════════════════════════════════════════════
# RUNNERS
# ═══════════════════════════════════════════════════════════════

def run_trustedge_simulation(config_name, config, seed):
    """Executa uma simulação TrustEdge."""
    env = os.environ.copy()
    params = config["params"]
    env['TRUSTEDGE_LOOKAHEAD'] = str(int(params['lookahead']))

    # Flags de módulos via variáveis de ambiente
    env['TRUSTEDGE_ENABLE_P2P'] = '1' if config.get('enable_p2p', True) else '0'
    env['TRUSTEDGE_ENABLE_LIVE_MIGRATION'] = '1' if config.get('enable_live_migration', True) else '0'
    env['TRUSTEDGE_ENABLE_FAILURE_PREDICTION'] = '1' if config.get('enable_failure_prediction', True) else '0'

    run_id = f"{config['scenario_id']}{seed}"

    cmd = [
        sys.executable, '-m', 'simulator',
        '--algorithm', config['algorithm'],
        '--seed', str(seed),
        '--time-steps', str(TIME_STEPS),
        '--input', DATASET,
        '--run-id', str(run_id),
        '--window-size', str(int(params['window_size'])),
        '--reliability-threshold', str(params['reliability_threshold']),
        '--delay-threshold', '1.0',
    ]

    start_t = time.time()
    try:
        result = subprocess.run(
            cmd, env=env, cwd=PROJECT_ROOT,
            capture_output=True, text=True, check=True
        )
        duration = time.time() - start_t
        print(f"  ✅ {config_name:<15} | Seed {seed:<5} | ID {run_id} | ⏱️ {duration:.1f}s")
        return True
    except subprocess.CalledProcessError as e:
        duration = time.time() - start_t
        print(f"  ❌ {config_name:<15} | Seed {seed:<5} | ID {run_id} | ⏱️ {duration:.1f}s")
        # Print last 3 lines of stderr for debugging
        stderr_lines = e.stderr.strip().split('\n')
        for line in stderr_lines[-3:]:
            print(f"     {line}")
        return False


def run_k8s_simulation(config_name, config, seed):
    """Executa uma simulação Kubernetes."""
    run_id = f"{config['scenario_id']}{seed}"

    cmd = [
        sys.executable, '-m', 'simulator',
        '--algorithm', config['algorithm'],
        '--seed', str(seed),
        '--time-steps', str(TIME_STEPS),
        '--input', DATASET,
        '--run-id', str(run_id),
    ]

    if config.get("enable_p2p"):
        cmd.append('--enable-p2p')
    if config.get("enable_live_migration"):
        cmd.append('--enable-live-migration')
    if config.get("enable_proactive_sla_migration"):
        cmd.append('--enable-proactive-sla-migration')
    if config.get("enable_failure_prediction"):
        cmd.append('--enable-failure-prediction')

    start_t = time.time()
    try:
        result = subprocess.run(
            cmd, cwd=PROJECT_ROOT,
            capture_output=True, text=True, check=True
        )
        duration = time.time() - start_t
        print(f"  ✅ {config_name:<15} | Seed {seed:<5} | ID {run_id} | ⏱️ {duration:.1f}s")
        return True
    except subprocess.CalledProcessError as e:
        duration = time.time() - start_t
        print(f"  ❌ {config_name:<15} | Seed {seed:<5} | ID {run_id} | ⏱️ {duration:.1f}s")
        stderr_lines = e.stderr.strip().split('\n')
        for line in stderr_lines[-3:]:
            print(f"     {line}")
        return False


def run_first_fit_simulation(config_name, config, seed):
    """Executa uma simulação First-Fit."""
    env = os.environ.copy()
    env['FF_ENABLE_P2P'] = '1' if config.get('enable_p2p', False) else '0'
    env['FF_ENABLE_LIVE_MIGRATION'] = '1' if config.get('enable_live_migration', False) else '0'
    env['FF_ENABLE_FAILURE_PREDICTION'] = '1' if config.get('enable_failure_prediction', False) else '0'

    run_id = f"{config['scenario_id']}{seed}"

    cmd = [
        sys.executable, '-m', 'simulator',
        '--algorithm', config['algorithm'],
        '--seed', str(seed),
        '--time-steps', str(TIME_STEPS),
        '--input', DATASET,
        '--run-id', str(run_id),
    ]

    start_t = time.time()
    try:
        result = subprocess.run(
            cmd, env=env, cwd=PROJECT_ROOT,
            capture_output=True, text=True, check=True
        )
        duration = time.time() - start_t
        print(f"  ✅ {config_name:<15} | Seed {seed:<5} | ID {run_id} | ⏱️ {duration:.1f}s")
        return True
    except subprocess.CalledProcessError as e:
        duration = time.time() - start_t
        print(f"  ❌ {config_name:<15} | Seed {seed:<5} | ID {run_id} | ⏱️ {duration:.1f}s")
        stderr_lines = e.stderr.strip().split('\n')
        for line in stderr_lines[-3:]:
            print(f"     {line}")
        return False


def _clean_only_new_results(scenario_ids):
    """Remove APENAS JSONs dos cenários NOVOS (não toca resultados existentes)."""
    results_dir = os.path.join(PROJECT_ROOT, "results")
    removed = 0
    for sid in scenario_ids:
        pattern = os.path.join(results_dir, f"metrics_run_{sid}*.json")
        for file_path in glob.glob(pattern):
            try:
                os.remove(file_path)
                removed += 1
            except OSError:
                pass
    if removed > 0:
        print(f"  🧹 Cleaned {removed} old JSON files from new scenarios only.")
    else:
        print(f"  ✅ No old files to clean.")


def _check_existing_results():
    """Verifica se os resultados existentes estão presentes."""
    results_dir = os.path.join(PROJECT_ROOT, "results")
    print(f"\n📋 Verificando resultados existentes (NÃO serão re-executados):")
    for name, info in EXISTING_SCENARIOS.items():
        sid = info["scenario_id"]
        pattern = os.path.join(results_dir, f"metrics_run_{sid}*.json")
        count = len(glob.glob(pattern))
        status = f"✅ {count}/{REPETITIONS} runs" if count >= REPETITIONS else f"⚠️ {count}/{REPETITIONS} runs"
        print(f"  {name:<15} (ID prefix {sid}): {status} — {info['description']}")
    print()


def _dispatch_wrapper(task):
    """Wrapper para starmap (precisa de função top-level)."""
    algo_type, name, config, seed = task
    if algo_type == "trustedge":
        return run_trustedge_simulation(name, config, seed)
    elif algo_type == "k8s":
        return run_k8s_simulation(name, config, seed)
    elif algo_type == "first_fit":
        return run_first_fit_simulation(name, config, seed)
    return False


def main():
    seeds = [BASE_SEED + i for i in range(REPETITIONS)]

    # ── Verificar resultados existentes ──
    _check_existing_results()

    # ── Montar tarefas APENAS para cenários NOVOS ──
    all_tasks = []

    for name, config in TRUSTEDGE_NEW_SCENARIOS.items():
        for seed in seeds:
            all_tasks.append(("trustedge", name, config, seed))

    for name, config in KUBERNETES_NEW_SCENARIOS.items():
        for seed in seeds:
            all_tasks.append(("k8s", name, config, seed))

    for name, config in FIRST_FIT_NEW_SCENARIOS.items():
        for seed in seeds:
            all_tasks.append(("first_fit", name, config, seed))

    total = len(all_tasks)
    total_existing = len(EXISTING_SCENARIOS) * REPETITIONS
    total_overall = total + total_existing

    print(f"{'='*70}")
    print(f"MODULAR VALIDATION EXPERIMENT")
    print(f"{'='*70}")
    print(f"  Existing results (preserved): {total_existing} runs ({len(EXISTING_SCENARIOS)} scenarios)")
    print(f"  New runs to execute:          {total} runs ({len(all_tasks) // REPETITIONS} scenarios)")
    print(f"  Total after completion:       {total_overall} runs (9 scenarios)")
    print(f"  Workers: {MAX_WORKERS}")
    print(f"")
    print(f"  New scenarios to run:")
    all_new = {**TRUSTEDGE_NEW_SCENARIOS, **KUBERNETES_NEW_SCENARIOS, **FIRST_FIT_NEW_SCENARIOS}
    for name, config in all_new.items():
        modules = []
        if config.get('enable_failure_prediction'):
            modules.append('FPM')
        if config.get('enable_p2p') or config.get('enable_live_migration'):
            modules.append('LTM')
        modules_str = '+'.join(modules) if modules else 'Default'
        print(f"    - {name:<15} (ID prefix {config['scenario_id']}) [{modules_str}]")
    print(f"{'='*70}\n")

    # ── Limpar APENAS resultados novos (preservar existentes) ──
    new_scenario_ids = [c["scenario_id"] for c in all_new.values()]
    _clean_only_new_results(new_scenario_ids)

    # ── Confirmar antes de executar ──
    print(f"\n⚠️  Resultados existentes (991, 994, 995) NÃO serão alterados.")
    response = input(f"Executar {total} novas simulações? (y/n): ").strip().lower()
    if response != 'y':
        print("Cancelado.")
        return

    print(f"\n🚀 Iniciando {total} simulações...\n")

    # ── Executar ──
    start_total = time.time()

    with multiprocessing.Pool(MAX_WORKERS) as pool:
        results = pool.starmap(_dispatch_wrapper, [(t,) for t in all_tasks])

    duration_total = time.time() - start_total
    success = sum(results)

    print(f"\n{'='*70}")
    print(f"🏁 COMPLETE")
    print(f"{'='*70}")
    print(f"  New runs:     {success}/{total} successful ({success/total*100:.1f}%)")
    print(f"  Existing:     {total_existing} preserved")
    print(f"  Total:        {success + total_existing}/{total_overall}")
    print(f"  Duration:     {duration_total/60:.1f} minutes")
    print(f"{'='*70}")

    if success < total:
        failed = [(t[1], t[3]) for t, r in zip(all_tasks, results) if not r]
        print(f"\n❌ Failed runs:")
        for name, seed in failed[:10]:
            print(f"  - {name} seed={seed}")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more")


if __name__ == "__main__":
    main()