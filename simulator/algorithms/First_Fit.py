"""
First-Fit Baseline - Algoritmo Guloso com Módulos Opcionais

Estratégia base:
- Seleciona o PRIMEIRO servidor disponível com capacidade
- NÃO considera latência, confiabilidade ou localidade de camadas

Módulos opcionais (habilitados via variáveis de ambiente):
- FPM (Failure Prediction Module): Predição Weibull + migração proativa
- LTM (Live Transfer Module): P2P download + Live Migration

Configurações:
- FF-D:        Reativo puro (Default)
- FF-FPM:      + Predição de falhas (migração proativa, cold)
- FF-FPM-LTM:  + Predição + P2P + Live Migration
"""

import os
from edge_sim_py import *
from simulator.helper_functions import *
from simulator.extensions import *

# ============================================================================
# GLOBAL METRICS
# ============================================================================

_first_fit_metrics = {
    "total_migrations": 0,
    "migrations_by_reason": {
        "server_failed": 0,
        "predicted_failure": 0,
    },
    "cold_migrations": 0,
    "live_migrations": 0,
    "by_step": {},
}

_ff_migration_cooldown = {}  # {service_id: last_migration_step}
FF_COOLDOWN_STEPS = 10  # Mínimo de steps entre migrações consecutivas

def reset_first_fit_metrics():
    global _first_fit_metrics, _ff_migration_cooldown
    _first_fit_metrics = {
        "total_migrations": 0,
        "migrations_by_reason": {
            "server_failed": 0,
            "predicted_failure": 0,
        },
        "cold_migrations": 0,
        "live_migrations": 0,
        "by_step": {},
    }
    _ff_migration_cooldown = {}


def increment_first_fit_migration(reason, current_step, is_live=False):
    global _first_fit_metrics
    _first_fit_metrics["total_migrations"] += 1

    if reason not in _first_fit_metrics["migrations_by_reason"]:
        _first_fit_metrics["migrations_by_reason"][reason] = 0
    _first_fit_metrics["migrations_by_reason"][reason] += 1

    if is_live:
        _first_fit_metrics["live_migrations"] += 1
    else:
        _first_fit_metrics["cold_migrations"] += 1

    if current_step not in _first_fit_metrics["by_step"]:
        _first_fit_metrics["by_step"][current_step] = 0
    _first_fit_metrics["by_step"][current_step] += 1


def print_first_fit_summary():
    metrics = _first_fit_metrics
    model = Topology.first()
    enable_p2p = getattr(model, '_ff_enable_p2p', False)
    enable_live = getattr(model, '_ff_enable_live', False)
    enable_prediction = getattr(model, '_ff_enable_prediction', False)

    config_name = "FF-D (Default)"
    if enable_prediction and (enable_p2p or enable_live):
        config_name = "FF-FPM-LTM"
    elif enable_prediction:
        config_name = "FF-FPM"

    print(f"\n{'='*70}")
    print(f"RESUMO FIRST-FIT BASELINE — {config_name}")
    print(f"{'='*70}")
    print(f"Módulos ativos:")
    print(f"  Failure Prediction (FPM): {'ON ✅' if enable_prediction else 'OFF ❌'}")
    print(f"  P2P Download:             {'ON ✅' if enable_p2p else 'OFF ❌'}")
    print(f"  Live Migration:           {'ON ✅' if enable_live else 'OFF ❌'}")
    print(f"")
    print(f"Total de migrações: {metrics['total_migrations']}")
    print(f"  Cold migrations:  {metrics['cold_migrations']}")
    print(f"  Live migrations:  {metrics['live_migrations']}")

    if metrics['total_migrations'] > 0:
        print(f"\nMigrações por motivo:")
        for reason, count in metrics['migrations_by_reason'].items():
            if count > 0:
                pct = (count / metrics['total_migrations']) * 100
                reason_name = {
                    "server_failed": "🔴 Falha de Servidor (reativa)",
                    "predicted_failure": "🟡 Predição de Falha (proativa FPM)",
                }.get(reason, reason)
                print(f"  - {reason_name}: {count} ({pct:.1f}%)")
        
        # ✅ NOVO: Diagnóstico de eficácia
        reactive_count = metrics['migrations_by_reason'].get('server_failed', 0)
        proactive_count = metrics['migrations_by_reason'].get('predicted_failure', 0)
        
        if enable_prediction and proactive_count == 0:
            print(f"\n⚠️ ALERTA: FPM habilitado mas ZERO migrações proativas!")
            print(f"   Possíveis causas:")
            print(f"     1. Cache Weibull não foi inicializado")
            print(f"     2. Nenhum servidor atingiu threshold de 50%")
            print(f"     3. Todos os destinos viáveis estavam cheios")

    print(f"{'='*70}\n")


# ============================================================================
# FIRST-FIT LOGIC
# ============================================================================

def first_fit_server_selection(service):
    """
    Seleciona o PRIMEIRO servidor disponível com capacidade.
    NÃO considera latência, confiabilidade ou localidade.
    """
    for server in EdgeServer.all():
        if not server.available:
            continue

        if server.has_capacity_to_host(service):
            return server

    return None


def reactive_migration_on_failure(current_step):
    """Migração reativa quando servidor falha."""
    model = Topology.first()
    use_live = getattr(model, '_ff_enable_live', False)

    for user in User.all():
        for app in user.applications:
            if not is_user_accessing_application(user, app, current_step):
                continue

            service = app.services[0]

            # Verificar se servidor falhou
            if service.server and not service.server.available:
                failed_server = service.server
                print(f"[FIRST-FIT] Servidor {failed_server.id} falhou — migrando serviço {service.id}")

                # Selecionar PRIMEIRO servidor disponível
                target_server = first_fit_server_selection(service)

                if not target_server:
                    print(f"[FIRST-FIT] ✗ Nenhum servidor disponível")
                    increment_first_fit_migration("server_failed", current_step, is_live=False)
                    continue

                if use_live:
                    # Live migration: serviço fica disponível na origem durante download
                    # (mas a origem falhou, então neste caso é cold de qualquer forma)
                    service._available = False
                    service.provision(target_server=target_server)
                else:
                    # Cold migration
                    service._available = False
                    service.provision(target_server=target_server)

                # Atualizar relacionamentos
                service.server = target_server
                if service not in target_server.services:
                    target_server.services.append(service)

                # Atualizar delay
                user.set_communication_path(app=app)
                new_delay = user._compute_delay(app=app, metric="latency")
                user.delays[str(app.id)] = new_delay

                print(f"[FIRST-FIT] ✓ Serviço recuperado no servidor {target_server.id}")
                # Falha de servidor é sempre cold (origem indisponível)
                increment_first_fit_migration("server_failed", current_step, is_live=False)


def ff_proactive_failure_migration(current_step):
    """Migração proativa First-Fit: mesmo módulo Weibull, seleção gulosa."""
    global _ff_migration_cooldown
    
    model = Topology.first()
    use_live = getattr(model, '_ff_enable_live', False)

    RELIABILITY_THRESHOLD = 50.0
    PREDICTION_HORIZON = 300

    if current_step == 1:
        print(f"[FF-FPM] ✅ Módulo de predição ATIVADO (threshold={RELIABILITY_THRESHOLD}%, horizon={PREDICTION_HORIZON})")

    servers_checked = 0
    servers_below_threshold = 0
    migrations_triggered = 0
    skipped_cooldown = 0
    skipped_no_improvement = 0

    for user in User.all():
        for app in user.applications:
            if not is_user_accessing_application(user, app, current_step):
                continue

            service = app.services[0]

            if not service.server or not service.server.available:
                continue

            # Pular se já está em migração ativa
            if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                last_mig = service._Service__migrations[-1]
                if last_mig.get("end") is None:
                    continue

            # Cooldown
            if service.id in _ff_migration_cooldown:
                last_step = _ff_migration_cooldown[service.id]
                if (current_step - last_step) < FF_COOLDOWN_STEPS:
                    skipped_cooldown += 1
                    continue

            server = service.server
            servers_checked += 1

            try:
                reliability = get_server_conditional_reliability_weibull(
                    server, PREDICTION_HORIZON
                )
            except Exception:
                reliability = 100.0

            if reliability < RELIABILITY_THRESHOLD:
                servers_below_threshold += 1

            if reliability >= RELIABILITY_THRESHOLD:
                continue

            target = first_fit_server_selection(service)

            if not target or target.id == server.id:
                continue

            try:
                target_reliability = get_server_conditional_reliability_weibull(
                    target, PREDICTION_HORIZON
                )
            except Exception:
                target_reliability = 100.0

            if target_reliability <= reliability:
                skipped_no_improvement += 1
                continue

            migrations_triggered += 1
            _ff_migration_cooldown[service.id] = current_step

            old_server = server

            if use_live:
                # ╔══════════════════════════════════════════════════════╗
                # ║ LIVE MIGRATION                                      ║
                # ║ 1. Chamar provision() para iniciar download         ║
                # ║ 2. RESTAURAR service.server para a origem           ║
                # ║ 3. service_step() fará o cutover quando terminar   ║
                # ╚══════════════════════════════════════════════════════╝

                # Disparar provision no target (isso inicia download de camadas)
                service.provision(target_server=target)

                # ✅ RESTAURAR ponteiro para a ORIGEM (Live Migration = rodar na origem)
                service.server = old_server
                if service not in old_server.services:
                    old_server.services.append(service)
                # Remover do target por enquanto (será adicionado no cutover pelo service_step)
                if service in target.services:
                    target.services.remove(service)

                # Manter serviço disponível no origin
                service._available = True

                # Configurar metadados da migração
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    migration = service._Service__migrations[-1]
                    migration["migration_reason"] = "predicted_failure"
                    migration["original_migration_reason"] = "predicted_failure"
                    migration["is_cold_migration"] = False
                    migration["origin"] = old_server
                    migration["target"] = target
                    migration["is_proactive"] = True
                    migration["relationships_created_by_algorithm"] = True

                print(f"[FF-FPM] ✓ LIVE migração: serviço {service.id} "
                      f"({old_server.id} → {target.id}), "
                      f"R={reliability:.1f}% → {target_reliability:.1f}%")

                increment_first_fit_migration(
                    "predicted_failure", current_step, is_live=True
                )

            else:
                # ╔══════════════════════════════════════════════════════╗
                # ║ COLD MIGRATION: serviço fica indisponível          ║
                # ╚══════════════════════════════════════════════════════╝
                service._available = False

                # Remover do servidor atual
                if service in old_server.services:
                    old_server.services.remove(service)
                old_server.cpu_demand = max(0, old_server.cpu_demand - service.cpu_demand)
                old_server.memory_demand = max(0, old_server.memory_demand - service.memory_demand)

                # Provisionar no target
                service.provision(target_server=target)

                # Atualizar relacionamentos
                service.server = target
                if service not in target.services:
                    target.services.append(service)
                target.cpu_demand += service.cpu_demand
                target.memory_demand += service.memory_demand

                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    migration = service._Service__migrations[-1]
                    migration["migration_reason"] = "predicted_failure"
                    migration["original_migration_reason"] = "predicted_failure"
                    migration["is_cold_migration"] = True
                    migration["origin"] = old_server
                    migration["target"] = target
                    migration["is_proactive"] = True
                    migration["relationships_created_by_algorithm"] = True

                print(f"[FF-FPM] ✓ COLD migração: serviço {service.id} "
                      f"({old_server.id} → {target.id}), "
                      f"R={reliability:.1f}% → {target_reliability:.1f}%")

                increment_first_fit_migration(
                    "predicted_failure", current_step, is_live=False
                )

            # Recalcular delay
            user.set_communication_path(app=app)
            new_delay = user._compute_delay(app=app, metric="latency")
            user.delays[str(app.id)] = new_delay

    if servers_checked > 0 or servers_below_threshold > 0:
        print(f"[FF-FPM] Step {current_step}: {servers_checked} verificados, "
              f"{servers_below_threshold} abaixo do threshold, "
              f"{migrations_triggered} migrações, "
              f"{skipped_cooldown} em cooldown, "
              f"{skipped_no_improvement} sem melhoria")
        
        
def first_fit_provision_service(user, app, service, current_step):
    """Provisiona um serviço usando First-Fit."""
    target = first_fit_server_selection(service)

    if not target:
        print(f"[FIRST-FIT] ✗ App {app.id}: sem servidor viável")
        return False

    service.server = target
    if service not in target.services:
        target.services.append(service)
    target.cpu_demand += service.cpu_demand
    target.memory_demand += service.memory_demand

    service.provision(target_server=target)

    # ✅ NOVO: Definir migration_reason para provisão inicial
    if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
        migration = service._Service__migrations[-1]
        migration["migration_reason"] = "Provision"
        migration["original_migration_reason"] = "Provision"
        migration["is_cold_migration"] = True
        migration["origin"] = None
        migration["target"] = target
        migration["relationships_created_by_algorithm"] = True

    user.set_communication_path(app=app)
    new_delay = user._compute_delay(app=app, metric="latency")
    user.delays[str(app.id)] = new_delay

    print(f"[FIRST-FIT] ✓ App {app.id} provisionada no servidor {target.id}")
    return True


def provision_new_requests(current_step):
    """Provisiona novas requisições usando First-Fit."""
    for user in User.all():
        if not is_making_request(user, current_step):
            continue

        for app in user.applications:
            service = app.services[0]

            # Pular se já está provisionado em servidor ativo
            if service.server and service.server.available:
                continue

            first_fit_provision_service(user, app, service, current_step)


def reactive_migration_on_failure(current_step):
    """Migração reativa quando servidor falha."""
    model = Topology.first()
    use_live = getattr(model, '_ff_enable_live', False)

    for user in User.all():
        for app in user.applications:
            if not is_user_accessing_application(user, app, current_step):
                continue

            service = app.services[0]

            # Verificar se servidor falhou
            if service.server and not service.server.available:
                failed_server = service.server
                print(f"[FIRST-FIT] Servidor {failed_server.id} falhou — migrando serviço {service.id}")

                # Selecionar PRIMEIRO servidor disponível
                target_server = first_fit_server_selection(service)

                if not target_server:
                    print(f"[FIRST-FIT] ✗ Nenhum servidor disponível")
                    increment_first_fit_migration("server_failed", current_step, is_live=False)
                    continue

                # ✅ Origem falhou → sempre cold (não há como manter na origem)
                service._available = False

                # ✅ Remover do servidor falhado
                if service in failed_server.services:
                    failed_server.services.remove(service)

                # ✅ Provisionar no novo servidor
                service.provision(target_server=target_server)

                # ✅ Atualizar relacionamentos
                service.server = target_server
                if service not in target_server.services:
                    target_server.services.append(service)

                # ✅ NOVO: Definir metadados da migração
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    migration = service._Service__migrations[-1]
                    migration["migration_reason"] = "server_failed"
                    migration["original_migration_reason"] = "server_failed"
                    migration["is_cold_migration"] = True
                    migration["origin"] = failed_server
                    migration["target"] = target_server
                    migration["is_proactive"] = False
                    migration["relationships_created_by_algorithm"] = True

                # Atualizar delay
                user.set_communication_path(app=app)
                new_delay = user._compute_delay(app=app, metric="latency")
                user.delays[str(app.id)] = new_delay

                print(f"[FIRST-FIT] ✓ Serviço {service.id} recuperado: "
                      f"{failed_server.id} → {target_server.id}")
                increment_first_fit_migration("server_failed", current_step, is_live=False)


# ============================================================================
# MAIN ALGORITHM
# ============================================================================

def first_fit_baseline(parameters: dict = {}):
    """First-Fit Baseline com módulos opcionais."""
    current_step = parameters.get("current_step")

    if current_step == 1:
        reset_first_fit_metrics()

        # Ler flags de módulos
        _ff_enable_p2p = os.environ.get('FF_ENABLE_P2P', '0') == '1'
        _ff_enable_live = os.environ.get('FF_ENABLE_LIVE_MIGRATION', '0') == '1'
        _ff_enable_prediction = os.environ.get('FF_ENABLE_FAILURE_PREDICTION', '0') == '1'

        # Armazenar no modelo
        model = Topology.first()
        model._ff_enable_p2p = _ff_enable_p2p
        model._ff_enable_live = _ff_enable_live
        model._ff_enable_prediction = _ff_enable_prediction

        # ✅ CORREÇÃO: Usar chaves corretas do dicionário retornado
        if _ff_enable_prediction:
            print(f"[FIRST-FIT] Inicializando cache de predição Weibull...")
            try:
                for server in EdgeServer.all():
                    if len(server.container_registries) > 0:
                        continue  # Pular registry
                    
                    # Forçar estimação inicial dos parâmetros Weibull
                    from simulator.helper_functions import estimate_weibull_parameters_from_history
                    params = estimate_weibull_parameters_from_history(server)
                    
                    if params and params.get('sample_size', 0) > 0:
                        # ✅ CORREÇÃO: Usar 'tbf_shape' e 'tbf_scale' em vez de 'shape' e 'scale'
                        shape = params.get('tbf_shape', 1.0)
                        scale = params.get('tbf_scale', 1000.0)
                        quality = params.get('estimation_quality', 'unknown')
                        sample_size = params.get('sample_size', 0)
                        
                        print(f"[FIRST-FIT] Server {server.id}: Weibull k={shape:.2f}, "
                              f"λ={scale:.1f}, quality={quality}, n={sample_size}")
                    else:
                        print(f"[FIRST-FIT] ⚠️ Server {server.id}: Sem histórico suficiente para Weibull")
                
                print(f"[FIRST-FIT] ✅ Cache de predição inicializado com sucesso\n")
            except Exception as e:
                print(f"[FIRST-FIT] ❌ Erro ao inicializar cache Weibull: {e}\n")
                import traceback
                traceback.print_exc()

        # Configurar módulos M3/M4 se habilitados
        try:
            from simulator.extensions.service_extensions import configure_migration_strategy
            configure_migration_strategy(
                enable_live_migration=_ff_enable_live,
                enable_state_transfer=_ff_enable_live,
            )
        except (ImportError, AttributeError):
            pass

        try:
            from simulator.extensions.edge_server_extensions import configure_layer_download
            configure_layer_download(
                enable_p2p=_ff_enable_p2p,
                enable_registry=True,
            )
        except ImportError:
            if _ff_enable_p2p:
                print(f"[FIRST-FIT] ⚠️ configure_layer_download não encontrado — P2P controlado via env var")
            pass

        # Determinar nome da configuração
        if _ff_enable_prediction and (_ff_enable_p2p or _ff_enable_live):
            config_name = "FF-FPM-LTM"
        elif _ff_enable_prediction:
            config_name = "FF-FPM"
        else:
            config_name = "FF-D (Default)"

        print(f"\n[FIRST-FIT] {'='*50}")
        print(f"[FIRST-FIT] First-Fit Baseline — {config_name}")
        print(f"[FIRST-FIT] {'='*50}")
        print(f"[FIRST-FIT] Module Configuration:")
        print(f"[FIRST-FIT]   Scheduling:              First-Fit (greedy)")
        print(f"[FIRST-FIT]   Failure Prediction (FPM): {'ON ✅' if _ff_enable_prediction else 'OFF ❌'}")
        print(f"[FIRST-FIT]   P2P Layer Download:       {'ON ✅' if _ff_enable_p2p else 'OFF ❌'}")
        print(f"[FIRST-FIT]   Live Migration:           {'ON ✅' if _ff_enable_live else 'OFF ❌'}")
        print(f"[FIRST-FIT] {'='*50}\n")

    print(f"\n[FIRST-FIT] === STEP {current_step} ===")

    # ══════════════════════════════════════════════════════════════
    # STEP 2: MIGRAÇÃO REATIVA (falhas de servidor) — SEMPRE ATIVA
    # ══════════════════════════════════════════════════════════════
    reactive_migration_on_failure(current_step)

    # ══════════════════════════════════════════════════════════════
    # STEP 3: MIGRAÇÃO PROATIVA (se FPM habilitado)
    # ══════════════════════════════════════════════════════════════
    model = Topology.first()
    if getattr(model, '_ff_enable_prediction', False):
        ff_proactive_failure_migration(current_step)

    # ══════════════════════════════════════════════════════════════
    # STEP 4: PROVISIONAR NOVAS REQUISIÇÕES
    # ══════════════════════════════════════════════════════════════
    provision_new_requests(current_step)

    # ══════════════════════════════════════════════════════════════
    # STEP 5: CLEANUP — Desprovisionamento + atualização de delays
    # ══════════════════════════════════════════════════════════════
    from simulator.algorithms.trust_edge_v3 import check_and_deprovision_inactive_services
    check_and_deprovision_inactive_services(current_step)

    from simulator.algorithms.trust_edge_v3 import update_application_delays
    update_application_delays(current_step)

    # ══════════════════════════════════════════════════════════════
    # STEP 6: COLETA DE MÉTRICAS
    # ══════════════════════════════════════════════════════════════
    collect_sla_violations_for_current_step()
    collect_infrastructure_metrics_for_current_step()
    update_user_perceived_downtime_for_current_step(current_step)

    # ══════════════════════════════════════════════════════════════
    # STEP 7: RELATÓRIO FINAL
    # ══════════════════════════════════════════════════════════════
    if parameters.get("time_steps") == current_step:
        print_first_fit_summary()

        # ══════════════════════════════════════════════════════════
        # STEP 8: SALVAR MÉTRICAS EM JSON
        # ══════════════════════════════════════════════════════════
        _save_first_fit_metrics_json(parameters)


def _save_first_fit_metrics_json(parameters):
    """Salva métricas do First-Fit em JSON compatível com validate_statistics.py."""
    import json as _json
    import time

    run_id = parameters.get("run_id")
    if run_id is None:
        return

    output_dir = "results"
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"metrics_run_{run_id}.json")

    # Se já existe (não deveria), não sobrescrever
    if os.path.exists(filepath):
        print(f"ℹ️  Métricas já existem em: {filepath}")
        return

    model = Topology.first()
    enable_p2p = getattr(model, '_ff_enable_p2p', False)
    enable_live = getattr(model, '_ff_enable_live', False)
    enable_prediction = getattr(model, '_ff_enable_prediction', False)

    # Determinar config name
    if enable_prediction and (enable_p2p or enable_live):
        config_name = "FF-FPM-LTM"
    elif enable_prediction:
        config_name = "FF-FPM"
    else:
        config_name = "FF-D"

    # ── Coletar SLA do sistema de métricas centralizado ──
    from simulator.helper_functions import collect_all_sla_violations, collect_all_infrastructure_metrics
    sla_metrics = collect_all_sla_violations()
    infra_metrics = collect_all_infrastructure_metrics()

    # ── Coletar avg_delay das latências brutas ──
    avg_delay = sla_metrics.get("avg_delay", 0)
    if avg_delay == 0:
        # Fallback: calcular dos delays atuais dos usuários
        all_delays = []
        for user in User.all():
            for app in user.applications:
                app_id = str(app.id)
                if app_id in user.delays:
                    d = user.delays[app_id]
                    if d != float('inf') and d > 0:
                        all_delays.append(d)
        if all_delays:
            avg_delay = sum(all_delays) / len(all_delays)

    # ── Métricas de migração do tracking interno ──
    metrics = _first_fit_metrics
    total_migrations = metrics["total_migrations"]

    # ── Prediction quality (se FPM habilitado) ──
    # First-Fit não tem tracking de TP/FP/FN, usar zeros
    prediction_quality = {
        "precision": 0,
        "recall": 0,
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
    }

    # ── Tempo de execução ──
    total_steps = parameters.get("time_steps", 1)
    exec_time_seconds = getattr(model, '_simulation_execution_time_seconds', 0)
    avg_time_per_step = exec_time_seconds / max(total_steps, 1)

    # ── Montar JSON no formato IDÊNTICO ao K8s e TrustEdge ──
    results = {
        "algorithm": config_name,
        "run_id": run_id,
        "seed": parameters.get("seed"),

        "sla": {
            "total_perceived_downtime": sla_metrics.get("total_perceived_downtime", 0),
            "total_delay_sla_violations": sla_metrics.get("total_delay_sla_violations", 0),
            "total_downtime_sla_violations": sla_metrics.get("total_downtime_sla_violations", 0),
            "avg_delay": round(avg_delay, 4),
        },

        "provisioning_and_migration": {
            "total_migrations": total_migrations,
            "migrations_by_original_reason": {
                "server_failed_unpredicted": metrics["migrations_by_reason"].get("server_failed", 0),
                "predicted_failure": metrics["migrations_by_reason"].get("predicted_failure", 0),
                "delay_violation": 0,
                "low_reliability": 0,
            },
            "cold_migrations": metrics["cold_migrations"],
            "live_migrations": metrics["live_migrations"],
        },

        "prediction_quality": prediction_quality,

        "execution": {
            "avg_time_per_step_seconds": round(avg_time_per_step, 6),
            "total_execution_seconds": round(exec_time_seconds, 2),
        },

        "infrastructure": {
            "average_overall_occupation": infra_metrics.get("average_overall_occupation", 0),
            "total_power_consumption": infra_metrics.get("total_power_consumption", 0),
        },

        "simulation_steps": total_steps,
    }

    with open(filepath, 'w') as f:
        _json.dump(results, f, indent=2, default=str)

    print(f"\n✅ [FIRST-FIT] Métricas salvas em: {filepath}")
    print(f"   Downtime: {results['sla']['total_perceived_downtime']}")
    print(f"   SLA Violations: {results['sla']['total_delay_sla_violations']}")
    print(f"   Migrations: {total_migrations}")