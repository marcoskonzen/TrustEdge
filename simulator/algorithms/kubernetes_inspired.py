# Importing EdgeSimPy components
from edge_sim_py import *

# Importing native Python modules/packages

import time

# Importing helper functions
from simulator.helper_functions import *

# Importing EdgeSimPy extensions
from simulator.extensions import *

"""
KUBERNETES STANDARD ALGORITHM FOR EDGE COMPUTING
Implements authentic Kubernetes behavior:
- Resource-based scheduling (CPU, RAM) - NO latency consideration
- QoS based on requests/limits (simulated via resource ratios)
- NO proactive migration
- NO automatic rebalancing
- Reactive pod recreation on node failures only
"""

"""
KUBERNETES STANDARD ALGORITHM FOR EDGE COMPUTING (Enhanced Version)
====================================================================

Implements authentic Kubernetes behavior with OPTIONAL enhancements:

BASELINE (Kubernetes Standard):
  - Resource-based scheduling (CPU, RAM) - NO latency consideration
  - QoS based on requests/limits
  - NO proactive migration
  - Reactive pod recreation on node failures only
  - Registry-only layer downloads

ENHANCEMENTS (Optional - configurable):
  - P2P Layer Download (edge servers share layers)
  - Live Migration (service stays available during pod recreation)

Usage:
  kubernetes_inspired(parameters={
      "current_step": 1,
      "enable_p2p": True,          # Enable P2P layer sharing
      "enable_live_migration": True # Enable live migration during failures
  })
"""

def k8s_check_and_deprovision_inactive_services(current_step):
    """
    Versão local K8S para limpar serviços (Pod Termination).
    """
    services_to_remove = []
    for user in User.all():
        for app in user.applications:
            # Se o usuário parou de acessar
            if not is_user_accessing_application(user, app, current_step):
                for service in app.services:
                    # ✅ NÃO remover se migração em andamento
                    if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                        last_migration = service._Service__migrations[-1]
                        if last_migration.get("end") is None:
                            continue

                    if service.server:
                        services_to_remove.append(service)
    
    for service in services_to_remove:
        # Libera recursos
        # Verifica se service.server ainda existe para evitar AttributeError em cascata
        if service.server:
            service.server.cpu_demand -= service.cpu_demand
            service.server.memory_demand -= service.memory_demand
            
            # ✅ CORREÇÃO: Verificar se disk_demand existe no serviço antes de subtrair
            if hasattr(service, 'disk_demand'):
                service.server.disk_demand -= service.disk_demand
            elif hasattr(service, 'disk'):
                 # Fallback raro se atributo chamar apenas 'disk'
                 service.server.disk_demand -= service.disk

            if service in service.server.services:
                service.server.services.remove(service)
            
            service.server = None
            service._available = False

# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

_K8S_CONFIG = {
    "enable_p2p": False,
    "enable_live_migration": False,
    "enable_proactive_sla_migration": False,
    "enable_failure_prediction": False,
}

_k8s_prediction_quality = {
        "proactive_migrations": [],
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
}

_k8s_total_execution_time = 0.0

def configure_kubernetes_enhancements(
    enable_p2p=False, 
    enable_live_migration=False,
    enable_proactive_sla_migration=False,
    enable_failure_prediction=False
):
    """
    Configura recursos OPCIONAIS para Kubernetes.
    
    Args:
        enable_p2p: Se True, habilita download P2P de camadas
        enable_live_migration: Se True, mantém pod disponível durante migração
        enable_proactive_sla_migration: Se True, migra ANTES da falha quando SLA é violado
    
    Examples:
        # Kubernetes PADRÃO (baseline)
        configure_kubernetes_enhancements(
            enable_p2p=False, 
            enable_live_migration=False,
            enable_proactive_sla_migration=False
        )
        
        # Kubernetes + Proactive SLA + Live Migration (TESTE REAL de Live Migration!)
        configure_kubernetes_enhancements(
            enable_p2p=True, 
            enable_live_migration=True,
            enable_proactive_sla_migration=True
        )
    """

    global _K8S_CONFIG
    _K8S_CONFIG["enable_p2p"] = enable_p2p
    _K8S_CONFIG["enable_live_migration"] = enable_live_migration
    _K8S_CONFIG["enable_proactive_sla_migration"] = enable_proactive_sla_migration
    _K8S_CONFIG["enable_failure_prediction"] = enable_failure_prediction
    
    
    # ✅ PROPAGATE: Configurar extensões
    from simulator.extensions.edge_server_extensions import configure_layer_download_strategy
    from simulator.extensions.service_extensions import configure_migration_strategy
    
    configure_layer_download_strategy(
        enable_p2p=enable_p2p,
        enable_registry=True
    )
    
    configure_migration_strategy(
        enable_live_migration=enable_live_migration,
        enable_state_transfer=True
    )
    
    print(f"\n[K8S_CONFIG] Kubernetes Enhancements Configured:")
    print(f"             - P2P Layer Download: {'ENABLED ✅' if enable_p2p else 'DISABLED ❌'}")
    print(f"             - Live Migration: {'ENABLED ✅' if enable_live_migration else 'DISABLED ❌'}")
    print(f"             - Proactive SLA Migration: {'ENABLED ✅' if enable_proactive_sla_migration else 'DISABLED ❌'}")
    print(f"             - Baseline: {'NO' if any([enable_p2p, enable_live_migration, enable_proactive_sla_migration]) else 'YES (Standard Kubernetes)'}\n")
    print(f"             - Failure Prediction: {'ENABLED ✅' if enable_failure_prediction else 'DISABLED ❌'}")

def get_kubernetes_config():
    """Retorna configuração atual do Kubernetes."""
    global _K8S_CONFIG 
    return _K8S_CONFIG.copy()

# ============================================================================
# ✅ SISTEMA DE MÉTRICAS DEDICADO DO KUBERNETES (Output Convergente)
# ============================================================================

# Estrutura espelho do TrustEdge para garantir compatibilidade do JSON
_k8s_metrics_store = {
    "total_provisionings": 0,
    "provisionings_finished": 0,
    "total_migrations": 0,
    "migrations_finished": 0,
    "migrations_interrupted": 0,
    # Mapeamento para garantir comparação correta nos gráficos
    "migrations_by_original_reason": {
        "server_failed_unpredicted": 0, # Mapeia para Reactive Pod Recreation
        "delay_violation": 0,           # Mapeia para Proactive Optimization
        "low_reliability": 0,           # Não usado no K8s (mas mantido para schema)
        "predicted_failure": 0,         # Não usado no K8s
    },
    "migration_times": {
        "all_migrations": [],
    }
}

def initialize_k8s_tracking():
    """Inicializa contadores exclusivos para a execução do Kubernetes."""
    global _k8s_metrics_store, _migration_counters
    
    # Resetar contadores granulares internos
    reset_migration_counters()
    
    # Resetar store de saída
    _k8s_metrics_store = {
        "total_provisionings": 0,
        "provisionings_finished": 0,
        "total_migrations": 0,
        "migrations_finished": 0,
        "migrations_interrupted": 0,
        "migrations_by_original_reason": {
            "server_failed_unpredicted": 0,
            "delay_violation": 0,
            "low_reliability": 0,
            "predicted_failure": 0,
        },
        "migration_times": {
            "all_migrations": [],
        }
    }

    _k8s_prediction_quality = {
        "proactive_migrations": [],
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
    }

def collect_k8s_final_metrics():
    """
    Consolida os contadores internos do Kubernetes (_migration_counters) 
    para o formato padrão de saída esperado pelos scripts de plotagem.
    """
    global _k8s_metrics_store, _migration_counters, _k8s_prediction_quality
    
    # 1. Migrações Totais
    total_migs = _migration_counters["total"]
    
    # Debug explícito
    print(f"[DEBUG_METRICS] Total Migrations Interno: {total_migs}")
    
    _k8s_metrics_store["total_migrations"] = total_migs
    _k8s_metrics_store["migrations_finished"] = _migration_counters["successful"]
    _k8s_metrics_store["migrations_interrupted"] = _migration_counters["failed"]
    
    # 2. Breakdown por Razão Dedução Matemática
    proactive_count = _migration_counters["by_reason"].get("delay_violation", 0)
    calculated_reactive = total_migs - proactive_count
    if calculated_reactive < 0: calculated_reactive = 0
    
    # ✅ ESTRATÉGIA DE ALIASING PARA COMPATIBILIDADE DE SCRIPTS
    _k8s_metrics_store["migrations_by_original_reason"] = {
        # Chave Padrão TrustEdge (Que o script de comparação provavelmente usa)
        "server_failed_unpredicted": calculated_reactive,
        
        # Chave Legacy/K8s (Que pode ser usada como fallback)
        "server_failed": calculated_reactive,
        
        # Chaves Proativas
        "delay_violation": proactive_count,
        "low_reliability": 0,    
        "predicted_failure": 0   
    }

    print(f"[DEBUG_METRICS] Exportando -> Reactive (Aliased): {calculated_reactive}, Proactive: {proactive_count}")
        
    # 3. Provisionamentos (Snapshot final)
    active_services = 0
    total_services = 0
    for user in User.all():
        for app in user.applications:
            total_services += 1
            if app.services[0].server:
                active_services += 1
    
    _k8s_metrics_store["total_provisionings"] = total_services
    _k8s_metrics_store["provisionings_finished"] = active_services
    
    pass

    print(f"[DEBUG_METRICS] Exportando -> Reactive: {calculated_reactive}, Proactive: {proactive_count}")
        
    tp = _k8s_prediction_quality["true_positives"]
    fp = _k8s_prediction_quality["false_positives"]
    fn = _k8s_prediction_quality["false_negatives"]
    
    precision = 0.0
    recall = 0.0
    
    if (tp + fp) > 0:
        precision = (tp / (tp + fp)) * 100
    
    if (tp + fn) > 0:
        recall = (tp / (tp + fn)) * 100
    
    _k8s_metrics_store["prediction_quality"] = {
        "precision": precision,
        "recall": recall,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "total_proactive_migrations": len(_k8s_prediction_quality["proactive_migrations"]),
    }
    
    print(f"[K8S_METRICS] Qualidade Preditiva:")
    print(f"              - Precision: {precision:.2f}%")
    print(f"              - Recall: {recall:.2f}%")
    print(f"              - TP: {tp}, FP: {fp}, FN: {fn}")

def get_k8s_metrics_export():
    """Retorna cópia das métricas para exportação JSON."""
    return _k8s_metrics_store.copy()

def get_migration_counters():
    return _migration_counters

def reset_migration_counters():
    global _migration_counters
    _migration_counters = {
        "total": 0,
        "by_reason": {
            "server_failed": 0,
            "delay_violation": 0,
            "low_reliability": 0
        },
        "by_step": {},
        "successful": 0,
        "failed": 0,
        "conversions": {
            "live_to_cold": 0,           # Origem falhou durante Live
            "target_recovery": 0,         # Destino falhou, encontrou novo
            "orphan_recovery": 0,         # Ambos falharam, encontrou novo
            "emergency_recovery": 0,      # Recuperação de emergência
            "fake_live_migrations": 0,      # Recuperação de emergência
        },
        "failures": {
            "target_failed": 0,           # Destino falhou
            "origin_failed": 0,           # Origem falhou
            "both_failed": 0,             # Ambos falharam
            "no_recovery_possible": 0,    # Sem servidor disponível
        }
    }

def increment_migration_counter(reason, current_step, success=True):
    """
    Incrementa contadores de migração de forma segura e centralizada.
    """
    global _migration_counters
    _migration_counters["total"] += 1
    
    # ✅ CORREÇÃO 1: Mapeamento de sinonimos para garantir consistência
    # O TrustEdge usa 'server_failed_unpredicted', o K8s usa 'server_failed'.
    # Vamos normalizar aqui ou garantir que a exportação trate isso.
    # Decisão: Manter 'server_failed' internamente e mapear na exportação.
    
    if reason not in _migration_counters["by_reason"]:
         # Inicializa se não existir
        _migration_counters["by_reason"][reason] = 0
        
    _migration_counters["by_reason"][reason] += 1
    
    if current_step not in _migration_counters["by_step"]:
        _migration_counters["by_step"][current_step] = 0
    _migration_counters["by_step"][current_step] += 1
    
    if success:
        _migration_counters["successful"] += 1
        status_str = "✓ SUCESSO"
    else:
        _migration_counters["failed"] += 1
        status_str = "✗ FALHA"
    
    print(f"[K8S_RECREATE] Pod recreado #{_migration_counters['total']}")
    print(f"               Motivo: {reason}")
    print(f"               Step: {current_step}")
    print(f"               Status: {status_str}")

def print_migration_summary():
    counters = get_migration_counters()
    
    print(f"\n{'='*60}")
    print(f"RESUMO DE RECRIAÇÕES DE PODS (Kubernetes Enhanced)")
    print(f"{'='*60}")
    print(f"Total de recriações: {counters['total']}")
    print(f"Recriações bem-sucedidas: {counters['successful']}")
    print(f"Recriações mal-sucedidas: {counters['failed']}")
    
    if counters['total'] > 0:
        success_rate = (counters['successful'] / counters['total']) * 100
        print(f"Taxa de sucesso: {success_rate:.2f}%")
    
    print(f"\nRecriações por motivo:")
    for reason, count in counters['by_reason'].items():
        if count > 0:
            percentage = (count / counters['total']) * 100
            print(f"  - {reason}: {count} ({percentage:.1f}%)")
    
    # ✅ NOVO: Resumo de conversões e recuperações
    conversions = counters.get("conversions", {})
    failures = counters.get("failures", {})
    
    total_conversions = sum(conversions.values())
    total_failures = sum(failures.values())
    
    if total_conversions > 0:
        print(f"\nConversões e Recuperações:")
        print(f"  - Live → Cold (origem falhou): {conversions.get('live_to_cold', 0)}")
        print(f"  - Novo destino (target falhou): {conversions.get('target_recovery', 0)}")
        print(f"  - Recuperação de órfão: {conversions.get('orphan_recovery', 0)}")
        print(f"  - Recuperação de emergência: {conversions.get('emergency_recovery', 0)}")
        print(f"  TOTAL: {total_conversions}")
    
    if total_failures > 0:
        print(f"\nTipos de Falhas Durante Migração:")
        print(f"  - Destino falhou: {failures.get('target_failed', 0)}")
        print(f"  - Origem falhou: {failures.get('origin_failed', 0)}")
        print(f"  - Ambos falharam: {failures.get('both_failed', 0)}")
        print(f"  - Sem recuperação possível: {failures.get('no_recovery_possible', 0)}")
        print(f"  TOTAL: {total_failures}")
    
    print(f"{'='*60}\n")

# ============================================================================
# KUBERNETES QOS CLASSES (baseado em resource requests/limits)
# ============================================================================

def classify_qos(service):
    """
    Classifica pod em classes QoS REAIS do Kubernetes:
    - Guaranteed: requests = limits para todos os recursos
    - Burstable: requests < limits OU apenas requests definidos
    - BestEffort: sem requests ou limits
    
    Simulação: baseado na razão demand/capacity do serviço
    """
    if not service:
        return "BestEffort"
    
    # Simular requests/limits baseado em demanda (usando helper functions)
    cpu_demand = get_normalized_demand(service)  # From helper_functions.py
    memory_demand = get_normalized_demand(service)  # Assumindo função similar para memória
    
    # Simular requests (70% da demanda) e limits (100% da demanda)
    cpu_requests = cpu_demand * 0.7
    cpu_limits = cpu_demand
    memory_requests = memory_demand * 0.7
    memory_limits = memory_demand
    
    # Verificar Guaranteed: requests == limits
    if cpu_requests == cpu_limits and memory_requests == memory_limits:
        return "Guaranteed"
    
    # Verificar BestEffort: sem demanda
    if cpu_demand == 0 and memory_demand == 0:
        return "BestEffort"
    
    # Caso padrão: Burstable
    return "Burstable"

def get_qos_priority(qos_class):
    """
    Retorna prioridade para eviction do Kubernetes:
    Guaranteed (3) > Burstable (2) > BestEffort (1)
    
    Durante resource pressure, Kubernetes evicta na ordem inversa.
    """
    priorities = {
        "Guaranteed": 3,
        "Burstable": 2,
        "BestEffort": 1
    }
    return priorities.get(qos_class, 0)

# ============================================================================
# KUBERNETES SCHEDULER (Filtering + Scoring)
# ============================================================================

def kubernetes_scheduler(service, user, application):
    """
    Implementa scheduler PADRÃO do Kubernetes (kube-scheduler) para EDGE:
    
    1. Filtering Phase (Predicates):
       - PodFitsResources: Node tem recursos suficientes
       - NodeCondition: Node está Ready
       
    2. Scoring Phase (Priorities):
       - NodeResourcesLeastAllocated (peso padrão: 1)
       - NodeResourcesBalancedAllocation (peso padrão: 1)
       
    ❌ REMOVIDO nesta versão:
       - ImageLocality: Não aplicável em edge geo-distribuído (sem registry compartilhado)
       
    IMPORTANTE: 
    - Kubernetes padrão NÃO considera latência/localização!
    - Kubernetes padrão NÃO considera SLA de delay!
    - Para edge computing, seria necessário custom scheduler (não implementado aqui).
    """
    
    # 1. FILTERING PHASE
    feasible_nodes = filter_feasible_nodes(service, user, application)
    
    if not feasible_nodes:
        print(f"[K8S_SCHEDULER] Nenhum node viável para app {application.id}")
        return None
    
    # 2. SCORING PHASE
    scored_nodes = score_nodes_standard(feasible_nodes, service, user, application)
    
    # 3. BINDING PHASE
    best_node = max(scored_nodes, key=lambda x: x["score"])
    
    print(f"[K8S_SCHEDULER] App {application.id} → Node {best_node['server'].id}")
    print(f"                Score: {best_node['score']:.2f}")
    print(f"                LeastAllocated: {best_node['least_allocated']:.3f}")
    print(f"                Balanced: {best_node['balanced']:.3f}")
    # ❌ REMOVIDO: print(f"                ImageLocality: {best_node['image_locality']:.3f}")
    
    return best_node["server"]

def filter_feasible_nodes(service, user, application):
    """
    Filtering Phase - Predicates do Kubernetes:
    
    1. PodFitsResources: Node tem CPU, memória e disco suficientes
    2. NodeCondition: Node está Ready (status == 'available')
    3. NodeUnschedulable: Node não está marcado como unschedulable
    
    Kubernetes NÃO filtra por latência ou localização!
    """
    feasible = []
    
    for server in EdgeServer.all():
        # Predicate: NodeCondition (node must be Ready)
        if server.status != "available":
            continue
        
        # Predicate: PodFitsResources
        if not server.has_capacity_to_host(service):
            continue
        
        # Node passou todos os predicates
        feasible.append(server)
    
    print(f"[K8S_FILTER] {len(feasible)}/{len(EdgeServer.all())} nodes viáveis")
    return feasible

def score_nodes_standard(nodes, service, user, application):
    """
    Scoring Phase - Priorities do Kubernetes PADRÃO (EDGE VERSION):
    
    Plugins ativos por padrão (todos com peso 1):
    1. NodeResourcesLeastAllocated: Favorece nodes com MAIS recursos livres
    2. NodeResourcesBalancedAllocation: Favorece nodes com uso balanceado
    
    ❌ REMOVIDO: ImageLocality
       Razão: No edge computing geo-distribuído, não há registry compartilhado.
              Kubernetes padrão não otimiza por cache de imagens em cenários edge.
    
    IMPORTANTE: Kubernetes padrão NÃO considera latência ou localização!
    """
    scored_nodes = []
    
    for server in nodes:
        total_score = 0.0
        
        # 1. NodeResourcesLeastAllocated (peso: 1, normalizado 0-10)
        cpu_allocatable = server.cpu
        cpu_requested = server.cpu_demand
        cpu_score = ((cpu_allocatable - cpu_requested) / cpu_allocatable) * 10 if cpu_allocatable > 0 else 0
        
        memory_allocatable = server.memory
        memory_requested = server.memory_demand
        memory_score = ((memory_allocatable - memory_requested) / memory_allocatable) * 10 if memory_allocatable > 0 else 0
        
        least_allocated_score = (cpu_score + memory_score) / 2  # 0-10
        total_score += least_allocated_score
        
        # 2. NodeResourcesBalancedAllocation (peso: 1, normalizado 0-10)
        cpu_fraction = cpu_requested / cpu_allocatable if cpu_allocatable > 0 else 0
        memory_fraction = memory_requested / memory_allocatable if memory_allocatable > 0 else 0
        
        mean = (cpu_fraction + memory_fraction) / 2
        variance = ((cpu_fraction - mean) ** 2 + (memory_fraction - mean) ** 2) / 2
        
        balanced_score = 10 - (variance * 10)  # 0-10
        balanced_score = max(0, balanced_score)
        total_score += balanced_score
        
        # ❌ REMOVIDO: ImageLocality
        # Kubernetes padrão em edge NÃO otimiza por cache (sem registry compartilhado)
        
        # Score final: soma direta (0-20), normalizada para 0-100
        normalized_score = (total_score / 20) * 100  # ← CORRIGIDO: /20 ao invés de /30
        
        scored_nodes.append({
            "server": server,
            "score": normalized_score,
            "least_allocated": least_allocated_score,
            "balanced": balanced_score,
            # ❌ REMOVIDO: "image_locality": image_score
        })
    
    return scored_nodes

# ============================================================================
# MAIN ALGORITHM
# ============================================================================

def kubernetes_inspired(parameters: dict = {}):
    global _raw_latencies, _k8s_total_execution_time 
    current_step = parameters.get("current_step")
    
    # ═══════════════════════════════════════════════════════════════════════
    # INICIALIZAÇÃO (PRIMEIRO STEP)
    # ═══════════════════════════════════════════════════════════════════════
    if current_step == 1:
            
        _raw_latencies = []
        _k8s_total_execution_time = 0.0
        initialize_k8s_tracking() 
        
        enable_p2p = parameters.get("enable_p2p", False)
        enable_live_migration = parameters.get("enable_live_migration", False)
        enable_proactive_sla_migration = parameters.get("enable_proactive_sla_migration", False)
        enable_failure_prediction = parameters.get("enable_failure_prediction", False)  # ✅ NOVO
        
        configure_kubernetes_enhancements(
            enable_p2p=enable_p2p,
            enable_live_migration=enable_live_migration,
            enable_proactive_sla_migration=enable_proactive_sla_migration,
            enable_failure_prediction=enable_failure_prediction  # ✅ NOVO
        )
        
        # ✅ NOVO: Inicializar cache Weibull se predição habilitada
        if enable_failure_prediction:
            from simulator.helper_functions import reset_weibull_estimation_cache
            try:
                reset_weibull_estimation_cache()
                print(f"[K8S] ✅ Weibull prediction cache initialized")
            except Exception as e:
                print(f"[K8S] ⚠️ Could not reset Weibull cache: {e}")
    step_start_time = time.process_time()
    
    # ═══════════════════════════════════════════════════════════════════════
    # PIPELINE PRINCIPAL (TODOS OS STEPS)
    # ═══════════════════════════════════════════════════════════════════════
    
    # 1. Provisionar novas requisições
    provision_new_requests(current_step)
    
    # 2. Desprovisionar serviços inativos (antes de atualizar delays)
    k8s_check_and_deprovision_inactive_services(current_step)
    
    # 3. ✅ ATUALIZAR DELAYS ANTES DE VERIFICAR VIOLAÇÕES
    update_application_delays(current_step)

    if current_step % 50 == 0:
        config = get_kubernetes_config()
        print(f"\n[K8S_DEBUG] Step {current_step}:")
        print(f"            enable_proactive_sla_migration = {config['enable_proactive_sla_migration']}")
        print(f"            _K8S_CONFIG = {_K8S_CONFIG}\n")
    
    # 4. Verificar violações de SLA (agora com delays atualizados!)
    check_and_migrate_sla_violations(current_step)

    k8s_proactive_failure_migration(current_step)
    
    # 5. Monitorar saúde das migrações
    monitor_migration_health_and_recover(current_step)
    
    # 6. Processar migrações em andamento
    process_ongoing_kubernetes_migrations(current_step)
    
    # 7. Recrear pods de servidores falhados
    reactive_pod_recreation(current_step)
    
    # 8. Coletar latências brutas (para CDF)
    for user in User.all():
        for app in user.applications:
            if is_user_accessing_application(user, app, current_step):
                app_id = str(app.id)
                if app_id in user.delays:
                    current_delay = user.delays[app_id]
                    if current_delay != float('inf') and current_delay > 0:
                        _raw_latencies.append(current_delay)
    
    # 9. Métricas de SLA e infraestrutura
    collect_sla_violations_for_current_step()
    collect_infrastructure_metrics_for_current_step()
    update_user_perceived_downtime_for_current_step(current_step)
    k8s_validate_predictions(current_step)
    
    step_duration = time.process_time() - step_start_time
    _k8s_total_execution_time += step_duration

    # ═══════════════════════════════════════════════════════════════════════
    # EXPORTAÇÃO FINAL (ÚLTIMO STEP)
    # ═══════════════════════════════════════════════════════════════════════
    if current_step == parameters.get("time_steps"):
        print(f"\n[K8S] ✅ Simulação concluída - Exportando resultados finais...")
        
        # ✅ NOVO: Coletar métricas locais
        collect_k8s_final_metrics()
        prov_mig_metrics = get_k8s_metrics_export()
        
        # Import Helper functions (SLA e Infra são genéricos, ok usar)
        from simulator.helper_functions import collect_all_sla_violations, collect_all_infrastructure_metrics
        sla_metrics = collect_all_sla_violations()
        infra_metrics = collect_all_infrastructure_metrics()
        
        migration_counters = get_migration_counters()
        config = get_kubernetes_config()
        
        # ═══════════════════════════════════════════════════════════════════
        # DETERMINAR SUFIXO DO ARQUIVO
        # ═══════════════════════════════════════════════════════════════════
        p2p = config["enable_p2p"]
        live = config["enable_live_migration"]
        sla = config["enable_proactive_sla_migration"]
        
        # ✅ LOG: Mostrar configuração detectada
        print(f"\n[K8S] 🔍 Configuração detectada:")
        print(f"      P2P: {'ON' if p2p else 'OFF'}")
        print(f"      Live Migration: {'ON' if live else 'OFF'}")
        print(f"      Proactive SLA: {'ON' if sla else 'OFF'}")
        
        # ✅ DETERMINAR SUFIXO (verificar combinações COMPLETAS primeiro!)
        if p2p and live and sla:
            config_suffix = "_p2p_live_sla"
        elif p2p and live:
            config_suffix = "_p2p_live"
        elif p2p and sla:
            config_suffix = "_p2p_sla"
        elif live and sla:
            config_suffix = "_live_sla"
        elif p2p:
            config_suffix = "_p2p"
        elif live:
            config_suffix = "_live"
        elif sla:
            config_suffix = "_sla"
        else:
            config_suffix = "_baseline"
        
        print(f"      Sufixo do arquivo: {config_suffix}")
        
        # ═══════════════════════════════════════════════════════════════════
        # ESTRUTURA DE RESULTADOS (IDÊNTICA AO TRUSTEDGE)
        # ═══════════════════════════════════════════════════════════════════
        total_steps = parameters.get("time_steps", 1)
        avg_time_per_step_ms = (_k8s_total_execution_time / total_steps) * 1000
        
        results = {
            "algorithm": f"Kubernetes{config_suffix.replace('_', ' ').title()}",
            "configuration": config,
            
            "sla": {
                "total_delay_sla_violations": sla_metrics.get("total_delay_sla_violations", 0),
                "total_perceived_downtime": sla_metrics.get("total_perceived_downtime", 0),
                "total_downtime_sla_violations": sla_metrics.get("total_downtime_sla_violations", 0),
                "avg_delay": sla_metrics.get("average_delay", 0) if "average_delay" in sla_metrics else (sum(_raw_latencies) / len(_raw_latencies) if _raw_latencies else 0),
                "exec_overhead_ms": avg_time_per_step_ms,
            },
            
            "infrastructure": {
                "average_overall_occupation": infra_metrics.get("average_overall_occupation", 0),
                "total_power_consumption": infra_metrics.get("total_power_consumption", 0),
            },
            
            "provisioning_and_migration": {
                "total_provisionings": prov_mig_metrics.get("total_provisionings", 0),
                "total_migrations": prov_mig_metrics.get("total_migrations", 0),
                "migrations_finished": prov_mig_metrics.get("migrations_finished", 0),
                "migrations_interrupted": prov_mig_metrics.get("migrations_interrupted", 0),
                
                # Mapeamento do dicionário local para o JSON
                "migrations_by_reason": prov_mig_metrics.get("migrations_by_original_reason", {}),
                
                # Breakdown reativo
                "server_failed_breakdown": {
                     "cold_migrations": migration_counters["by_reason"].get("server_failed", 0),
                     "hot_migrations": 0 # K8s reactive é sempre cold start
                },
                
                "avg_migration_time": 0, # Opcional ou calcular
                "downtime_breakdown": {}, # Deixar vazio ou preencher se rastrear
            },
            
            "raw_latencies": _raw_latencies,
            "total_latency_samples": len(_raw_latencies),
            
            "legacy_metrics": {
                "total_migrations": migration_counters["total"],
                "migrations_successful": migration_counters["successful"],
                "migrations_failed": migration_counters["failed"],
                "migrations_by_reason": migration_counters["by_reason"],
            },
            
            "prediction_quality": _k8s_metrics_store.get("prediction_quality", {
                "precision": 0,
                "recall": 0,
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
            }),

            "execution": {
                "avg_time_per_step_seconds": _k8s_total_execution_time / total_steps,
            },

            "simulation_steps": parameters.get("time_steps", 0),
        }
        
        # ═══════════════════════════════════════════════════════════════════
        # SALVAR ARQUIVO JSON
        # ═══════════════════════════════════════════════════════════════════
        import os
        import json
        
        os.makedirs("results", exist_ok=True)
        run_id = parameters.get("run_id")
        if run_id is not None:
            output_file = f"results/metrics_run_{run_id}.json"
        else:
            output_file = f"results/k8s{config_suffix}_results.json"
        
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        
        # ═══════════════════════════════════════════════════════════════════
        # LOG FINAL
        # ═══════════════════════════════════════════════════════════════════
        print("\n" + "="*70)
        print(f"✅ [PAPER] Resultados Kubernetes{config_suffix.replace('_', ' ').title()} exportados")
        print(f"   Arquivo: {output_file}")
        print(f"   Configuração: P2P={'ON' if p2p else 'OFF'} | Live={'ON' if live else 'OFF'} | SLA={'ON' if sla else 'OFF'}")
        print(f"   Downtime Total: {sla_metrics.get('total_perceived_downtime', 0)} steps")
        print(f"   SLA Violations: {sla_metrics.get('total_delay_sla_violations', 0)}")
        print(f"   Latências coletadas: {len(_raw_latencies)}")
        print(f"   Migrações totais: {prov_mig_metrics.get('total_migrations', 0)}")
        print(f"   Migrações finalizadas: {prov_mig_metrics.get('migrations_finished', 0)}")
        print("="*70 + "\n")
        
        print_migration_summary()

# ============================================================================
# FUNÇÕES HELPER PARA CÁLCULO DE MÉTRICAS
# ============================================================================

def calculate_total_downtime():
    """
    Calcula downtime total percebido pelos usuários.
    Usa a mesma lógica do TrustEdge mas localmente.
    """
    total_downtime = 0
    
    for user in User.all():
        for app in user.applications:
            app_id = str(app.id)
            
            # Acessar histórico de downtime do usuário
            if hasattr(user, 'downtime_history') and app_id in user.downtime_history:
                app_downtime = sum(user.downtime_history[app_id])
                total_downtime += app_downtime
    
    return total_downtime

def calculate_total_sla_violations():
    """
    Calcula total de violações de SLA de latência.
    Usa a mesma lógica do TrustEdge mas localmente.
    """
    total_violations = 0
    
    for user in User.all():
        for app in user.applications:
            app_id = str(app.id)
            
            # Verificar se aplicação tem SLA de delay definido
            if hasattr(app, 'delay_sla') and app.delay_sla:
                delay_sla = app.delay_sla
                
                # Pegar delay atual
                if app_id in user.delays:
                    current_delay = user.delays[app_id]
                    
                    # Verificar violação
                    if current_delay > delay_sla and current_delay != float('inf'):
                        total_violations += 1
    
    return total_violations

# ============================================================================
# REACTIVE POD RECREATION (não é migração, é recreação)
# ============================================================================

def reactive_pod_recreation(current_step):
    """
    Simula o comportamento padrão do Kubernetes de recriar pods quando um node falha.
    """
    print(f"\n[K8S] === VERIFICAÇÃO DE NODE FAILURES (REACTIVE) - STEP {current_step} ===")
    
    # Identificar serviços em servidores falhados
    services_to_recover = []
    
    for service in Service.all():
        if service.server and not service.server.available:
            services_to_recover.append(service)
    
    if not services_to_recover:
        return

    # ✅ CORREÇÃO: Rastrear servidores já contabilizados como FN
    if _K8S_CONFIG.get('enable_failure_prediction', False):
        global _k8s_prediction_quality
        
        # ✅ NOVO: Set para evitar duplicação
        failed_servers_seen = set()
        
        for service in services_to_recover:
            failed_server = service.server
            
            # ✅ CORREÇÃO: Pular se já contabilizamos este servidor
            if failed_server.id in failed_servers_seen:
                continue
            
            failed_servers_seen.add(failed_server.id)
            
            # Verificar se essa falha foi prevista
            was_predicted = any(
                item["server_id"] == failed_server.id and not item.get("validated", False)
                for item in _k8s_prediction_quality["proactive_migrations"]
            )
            
            if not was_predicted:
                # FALSE NEGATIVE: Servidor falhou mas não previmos
                _k8s_prediction_quality["false_negatives"] += 1
                
                print(f"[K8S_VALIDATE] ⚠️ FN: Server {failed_server.id} falhou sem previsão "
                      f"(step {current_step})")

    print(f"[K8S] {len(services_to_recover)} serviços perderam seus nodes. Iniciando recriação...")

    for service in services_to_recover:
        user = service.application.users[0]
        app = service.application
        failed_server = service.server
        
        print(f"[K8S] Serviço {service.id} (App {app.id}) estava no servidor {failed_server.id} (FALHOU)")
        
        # Kubernetes Scheduler Logic: Escolher node com recursos disponíveis
        candidates = [s for s in EdgeServer.all() if s.status == "available" and s.has_capacity_to_host(service)]
        
        if candidates:
            # ✅ CORREÇÃO 1: Passar 'user' e 'app' que faltavam (causava o TypeError)
            scored_candidates = score_nodes_standard(candidates, service, user, app)
            
            # ✅ CORREÇÃO 2: Selecionar o servidor do dicionário de score (causava erro de provision)
            best_node_data = max(scored_candidates, key=lambda x: x["score"])
            target_server = best_node_data["server"]
            
            try:
                # Provisionar no novo servidor (Cold Migration forçada)
                service.provision(target_server=target_server)
                
                # ✅ GARANTIA DE METADADOS
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    migration = service._Service__migrations[-1]
                    
                    migration["migration_reason"] = "server_failed"
                    migration["original_migration_reason"] = "server_failed" # CRÍTICO PARA O RELATÓRIO
                    migration["is_cold_migration"] = True
                    
                    if migration.get("origin") is None:
                         migration["origin"] = failed_server
                
                # Atualizar delays para refletir novo posicionamento
                user.set_communication_path(app=app)
                new_delay = user._compute_delay(app=app, metric="latency")
                user.delays[str(app.id)] = new_delay
                
                print(f"[K8S] ✓ Novo pod criado no node {target_server.id}")
                increment_migration_counter("server_failed", current_step, success=True)
                print(f"      Delay resultante: {new_delay:.2f}ms")
                    
            except Exception as e:
                print(f"[K8S] ✗ Erro ao recriar pod: {e}")
                import traceback
                traceback.print_exc()
                increment_migration_counter("server_failed", current_step, success=False)
                
                if target_server and hasattr(target_server, 'ongoing_migrations'):
                    target_server.ongoing_migrations -= 1
                
        else:
            print(f"[K8S] ✗ Nenhum node disponível para recriar pod")
            increment_migration_counter("server_failed", current_step, success=False)

    print(f"[K8S] === FIM VERIFICAÇÃO DE NODE FAILURES ===\n")


# ============================================================================
# PREDIÇÃO DE FALHAS PARA KUBERNETES ENHANCED
# ============================================================================

def k8s_proactive_failure_migration(current_step):
    if not _K8S_CONFIG.get('enable_failure_prediction', False):
        return
    
    # ✅ LOGGING DETALHADO A CADA 100 STEPS
    if current_step % 100 == 0:
        print(f"\n[K8S_PREDICT] === DIAGNÓSTICO STEP {current_step} ===")
    
    RELIABILITY_THRESHOLD = 50.0  # ← Reduzido
    PREDICTION_HORIZON = 300
    
    migrations_triggered = 0
    servers_checked = 0
    servers_skipped = {
        "no_server": 0,
        "server_unavailable": 0,
        "in_migration": 0,
        "no_weibull_params": 0,
        "reliability_above_threshold": 0,
        "no_predictions": 0,
        "no_viable_target": 0,
    }
    
    for service in Service.all():
        if not service.server:
            servers_skipped["no_server"] += 1
            continue
        
        if not service.server.available:
            servers_skipped["server_unavailable"] += 1
            continue
        
        if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
            last_migration = service._Service__migrations[-1]
            if last_migration.get("end") is None:
                servers_skipped["in_migration"] += 1
                continue
        
        server = service.server
        servers_checked += 1
        
        # ✅ VERIFICAR HISTÓRICO
        if hasattr(server, 'failure_model') and hasattr(server.failure_model, 'failure_history'):
            history_len = len(server.failure_model.failure_history)
            if history_len < 3:
                servers_skipped["no_weibull_params"] += 1
                if current_step % 100 == 0:
                    print(f"[K8S_PREDICT] Server {server.id}: Histórico insuficiente ({history_len} falhas)")
                continue
        else:
            servers_skipped["no_weibull_params"] += 1
            continue
        
        from simulator.helper_functions import (
            get_server_conditional_reliability_weibull,
            predict_next_n_failures,
        )
        
        try:
            reliability = get_server_conditional_reliability_weibull(server, PREDICTION_HORIZON)
        except Exception as e:
            servers_skipped["no_weibull_params"] += 1
            if current_step % 100 == 0:
                print(f"[K8S_PREDICT] ⚠️ Erro Weibull Server {server.id}: {e}")
            continue
        
        if reliability >= RELIABILITY_THRESHOLD:
            servers_skipped["reliability_above_threshold"] += 1
            continue
        
        predictions = predict_next_n_failures(server, n_failures=2, max_horizon=PREDICTION_HORIZON)
        
        if not predictions:
            servers_skipped["no_predictions"] += 1
            continue
        
        # ✅ LOGGING: Servidor elegível para migração
        if current_step % 100 == 0:
            print(f"[K8S_PREDICT] ✅ Server {server.id}: reliability={reliability:.1f}%, {len(predictions)} falhas previstas")
        
        # ══════════════════════════════════════════════════════════
        # DECISÃO K8S: Scheduler PADRÃO para escolher destino
        # (SEM trust_cost, SEM SLA awareness, SEM STAY vs GO)
        # ══════════════════════════════════════════════════════════
        app = service.application
        user = app.users[0] if app.users else None
        
        if not user or not is_user_accessing_application(user, app, current_step):
            continue
        
        # Usar scheduler K8s padrão (CPU/RAM only)
        target = kubernetes_scheduler(service, user, app)
        
        if not target or target.id == server.id:
            print(f"[K8S_PREDICT] ❌ Sem destino viável para service {service.id}")
            continue
        
        global _k8s_prediction_quality
        _k8s_prediction_quality["proactive_migrations"].append({
            "service_id": service.id,
            "server_id": server.id,
            "step": current_step,
            "reason": "predicted_failure",
            "validated": False,
            "validation_window": PREDICTION_HORIZON,  # 100 steps
            "deadline": current_step + PREDICTION_HORIZON,
            "reliability_at_prediction": reliability,
            "predictions_count": len(predictions),
        })

        # ══════════════════════════════════════════════════════════
        # EXECUTAR MIGRAÇÃO (Live ou Cold conforme config)
        # ══════════════════════════════════════════════════════════
        use_live = _K8S_CONFIG['enable_live_migration']
        origin_server = service.server
        
        try:
            if use_live:
                service._available = True
                service._migration_reason = "predicted_failure"
                target.ongoing_migrations += 1
                service.provision(target_server=target)

                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    migration = service._Service__migrations[-1]
                    migration["migration_reason"] = "predicted_failure"
                    migration["original_migration_reason"] = "predicted_failure"
                    migration["is_cold_migration"] = False
                    migration["origin"] = origin_server
                    migration["target"] = target
                    migration["is_proactive"] = True
                    migration["relationships_created_by_algorithm"] = True
                    migration["k8s_prediction_data"] = {
                        "reliability": reliability,
                        "threshold": RELIABILITY_THRESHOLD,
                        "predictions": len(predictions),
                    }
            else:
                service._available = False
                service._migration_reason = "predicted_failure"
                target.ongoing_migrations += 1
                service.provision(target_server=target)
                
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    migration = service._Service__migrations[-1]
                    migration["migration_reason"] = "predicted_failure"
                    migration["original_migration_reason"] = "predicted_failure"
                    migration["is_cold_migration"] = True
                    migration["origin"] = origin_server
                    migration["target"] = target
                    migration["is_proactive"] = True
            
            increment_migration_counter("predicted_failure", current_step, success=True)
            migrations_triggered += 1
            
            print(f"[K8S_PREDICT] ✅ Migração proativa: Service {service.id} → Server {target.id}")
            
        except Exception as e:
            print(f"[K8S_PREDICT] ❌ Erro ao migrar service {service.id}: {e}")
            if target and hasattr(target, 'ongoing_migrations'):
                target.ongoing_migrations = max(0, target.ongoing_migrations - 1)
            increment_migration_counter("predicted_failure", current_step, success=False)
    
    if current_step % 100 == 0:
        print(f"[K8S_PREDICT] Servidores verificados: {servers_checked}")
        print(f"[K8S_PREDICT] Migrações disparadas: {migrations_triggered}")
        print(f"[K8S_PREDICT] Razões de exclusão:")
        for reason, count in servers_skipped.items():
            if count > 0:
                print(f"              - {reason}: {count}")
        print(f"[K8S_PREDICT] === FIM DIAGNÓSTICO ===\n")


def process_ongoing_kubernetes_migrations(current_step):
    """
    Processa migrações em andamento do Kubernetes.
    
    IMPORTANTE: Necessário para decrementar contadores e finalizar migrações.
    ✅ CORREÇÃO: Processar TODOS os tipos de migração (não apenas server_failed).
    """
    migrations_completed = 0
    migrations_failed = 0
    
    for service in Service.all():
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            continue
        
        migration = service._Service__migrations[-1]
        
        # Pular migrações já finalizadas
        if migration.get("end") is not None:
            continue
        
        # ✅ CORREÇÃO: REMOVER filtro que exclui delay_violation
        # ANTES: if migration.get("migration_reason") != "server_failed": continue
        # DEPOIS: Processar TODAS as migrações
        
        status = migration.get("status", "unknown")
        target = migration.get("target")
        is_live = not migration.get("is_cold_migration", False)
        migration_reason = migration.get("migration_reason", "unknown")
        
        # ✅ Verificar se migração foi completada
        if status == "finished":
            migrations_completed += 1
            
            # Decrementar contador do servidor de destino
            if target and hasattr(target, 'ongoing_migrations'):
                target.ongoing_migrations = max(0, target.ongoing_migrations - 1)
            
            migration_type = "Live" if is_live else "Cold"
            print(f"[K8S_MIG] ✅ Migração {migration_type} completada: Service {service.id} → Server {target.id} (Motivo: {migration_reason})")
        
        # ✅ Verificar se falhou (servidor de destino falhou)
        elif target and not target.available:
            migration["end"] = current_step
            migration["status"] = "interrupted"
            migration["interruption_reason"] = "target_server_failed"
            
            migrations_failed += 1
            
            if target and hasattr(target, 'ongoing_migrations'):
                target.ongoing_migrations = max(0, target.ongoing_migrations - 1)
            
            print(f"[K8S_MIG] ❌ Migração falhou: Service {service.id} (target falhou, motivo original: {migration_reason})")
    
    if migrations_completed > 0 or migrations_failed > 0:
        print(f"[K8S_MIG] Migrações processadas: {migrations_completed} completas, {migrations_failed} falhadas")



# ============================================================================
# PROVISIONING (scheduling acontece APENAS aqui)
# ============================================================================

def provision_new_requests(current_step):
    """
    Provisiona novos pods.
    
    Kubernetes PADRÃO:
    - Scheduling acontece apenas na criação do pod
    - Decisão é permanente até pod ser deletado
    - SEM rebalanceamento automático
    - SEM otimização contínua
    """
    print(f"\n[K8S] === SCHEDULING DE NOVOS PODS - STEP {current_step} ===")
    
    apps_to_provision = []
    
    for user in User.all():
        if is_making_request(user, current_step):
            for app in user.applications:
                service = app.services[0]
                qos_class = classify_qos(service)
                
                apps_to_provision.append({
                    "application": app,
                    "user": user,
                    "service": service,
                    "qos_class": qos_class,
                    "qos_priority": get_qos_priority(qos_class)
                })
    
    if not apps_to_provision:
        print(f"[K8S] Nenhum novo pod para provisionar")
        return
    
    # Ordenar por QoS priority
    apps_to_provision.sort(key=lambda x: x["qos_priority"], reverse=True)
    
    print(f"[K8S] {len(apps_to_provision)} novos pods para provisionar")
    
    for item in apps_to_provision:
        app = item["application"]
        user = item["user"]
        service = item["service"]
        qos_class = item["qos_class"]
        
        print(f"\n[K8S] Scheduling pod {service.id} (QoS: {qos_class})")
        
        # Usar scheduler padrão do Kubernetes
        target_server = kubernetes_scheduler(service, user, app)
        
        if target_server:
            service.provision(target_server=target_server)
            
            user.set_communication_path(app=app)
            new_delay = user._compute_delay(app=app, metric="latency")
            user.delays[str(app.id)] = new_delay
            
            print(f"[K8S] ✓ Pod criado no node {target_server.id}")
            print(f"      Delay resultante: {new_delay:.2f}ms")
            print(f"      AVISO: Pod permanecerá neste node até ser deletado")
        else:
            print(f"[K8S] ✗ Nenhum node disponível - pod fica Pending")
    
    print(f"[K8S] === FIM SCHEDULING DE NOVOS PODS ===\n")

def update_application_delays(current_step):
    """
    Atualiza delays de TODAS as aplicações ativas.
    
    ✅ CORREÇÃO: Atualizar mesmo se is_making_request() for True.
    """
    
    # ✅ ADICIONAR: Contadores de debug
    delays_updated = 0
    delays_set_to_inf = 0
    delays_skipped = 0
    sample_delays = []  # Amostra para debug
    
    for user in User.all():
        for app in user.applications:
            service = app.services[0]
            app_id = str(app.id)
            
            if is_user_accessing_application(user, app, current_step):
                if service.server and service.server.status == "available" and service._available:
                    user.set_communication_path(app=app)
                    new_delay = user._compute_delay(app=app, metric="latency")
                    user.delays[app_id] = new_delay
                    delays_updated += 1
                    
                    # ✅ ADICIONAR: Coletar amostra para debug
                    if len(sample_delays) < 5:  # Primeiros 5
                        sla = getattr(app, 'delay_sla', None)
                        sample_delays.append({
                            'app_id': app.id,
                            'delay': new_delay,
                            'sla': sla,
                            'violated': new_delay > sla if sla else False
                        })
                else:
                    # Serviço indisponível
                    user.delays[app_id] = float('inf')
                    delays_set_to_inf += 1
            else:
                delays_skipped += 1
    
    # ✅ ADICIONAR: LOG a cada 50 steps
    if current_step % 50 == 0:
        print(f"\n[K8S_DELAYS] Step {current_step}:")
        print(f"             - Delays atualizados: {delays_updated}")
        print(f"             - Setados para inf: {delays_set_to_inf}")
        print(f"             - Não acessando: {delays_skipped}")
        
        if sample_delays:
            print(f"\n[K8S_DELAYS] 🔍 Amostra de delays (primeiros 5):")
            for i, d in enumerate(sample_delays):
                sla_str = f"{d['sla']:.2f}ms" if d['sla'] else "SEM SLA"
                status = "VIOLADO ❌" if d['violated'] else "OK ✅"
                print(f"             {i+1}. App {d['app_id']}: {d['delay']:.2f}ms / SLA={sla_str} [{status}]")

def get_active_applications_with_remaining_time(user, current_step):
    """Retorna aplicações ativas com informações de tempo."""
    active_applications = []
    
    for application in user.applications:
        if is_user_accessing_application(user, application, current_step):
            app_id = str(application.id)
            last_access = user.access_patterns[app_id].history[-1]
            remaining_time = last_access["end"] - current_step
            
            active_applications.append({
                "application": application,
                "remaining_time": remaining_time,
                "total_duration": last_access["duration"],
                "access_start": last_access["start"],
                "access_end": last_access["end"]
            })
    
    return active_applications


def check_and_migrate_sla_violations(current_step):
    """
    ✅ NOVA ESTRATÉGIA: Migração Proativa para OTIMIZAÇÃO de Desempenho
    
    Migra quando:
    1. Existe servidor com delay >= 15% MELHOR que atual
    2. Servidor tem capacidade disponível
    3. Minimiza downtime percebido
    
    IMPORTANTE: 
    - NÃO espera violação de SLA
    - Migra SEMPRE que houver oportunidade de melhoria significativa
    - Usa limiar de 15% para evitar migrações triviais
    """
    
    if not _K8S_CONFIG['enable_proactive_sla_migration']:
        return
    
    print(f"\n[K8S_OPT] === VERIFICAÇÃO DE OTIMIZAÇÃO DE DESEMPENHO - STEP {current_step} ===")
    
    apps_checked = 0
    migrations_triggered = 0
    
    # ✅ PARÂMETRO: Limiar de melhoria mínima para migração (15%)
    IMPROVEMENT_THRESHOLD = 0.15  # 15% de melhoria mínima
    
    for user in User.all():
        active_applications = get_active_applications_with_remaining_time(user, current_step)
        
        for app_info in active_applications:
            app = app_info["application"]
            service = app.services[0]
            
            apps_checked += 1
            
            # PRÉ-REQUISITO 1: Servidor atual deve estar disponível
            if not service.server or service.server.status != "available":
                continue
            
            # PRÉ-REQUISITO 2: Não há migração em andamento
            if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                last_migration = service._Service__migrations[-1]
                if last_migration.get("end") is None:
                    continue
            
            # ═══════════════════════════════════════════════════════════
            # BUSCAR SERVIDOR MELHOR (delay X% menor)
            # ═══════════════════════════════════════════════════════════
            
            app_id = str(app.id)
            current_delay = user.delays.get(app_id, float('inf'))
            
            # Pular se delay atual é infinito (serviço indisponível)
            if current_delay == float('inf'):
                continue
            
            # Pular se delay atual é muito baixo (< 10ms) - sem ganho significativo
            if current_delay < 10:
                continue
            
            # Procurar servidor com delay significativamente MELHOR
            best_server, best_delay = find_significantly_better_server(
                service, user, app, current_delay, IMPROVEMENT_THRESHOLD
            )
            
            if not best_server:
                continue  # Nenhum servidor melhor encontrado
            
            # Não migrar se for o mesmo servidor
            if best_server.id == service.server.id:
                continue
            
            # ═══════════════════════════════════════════════════════════
            # CALCULAR GANHO DE DESEMPENHO
            # ═══════════════════════════════════════════════════════════
            
            delay_reduction = current_delay - best_delay
            improvement_pct = (delay_reduction / current_delay) * 100
            
            print(f"\n[K8S_OPT] 🎯 Oportunidade de otimização detectada:")
            print(f"          App: {app.id}, User: {user.id}")
            print(f"          Servidor atual: {service.server.id} (delay: {current_delay:.2f}ms)")
            print(f"          Servidor melhor: {best_server.id} (delay: {best_delay:.2f}ms)")
            print(f"          Melhoria: {delay_reduction:.2f}ms ({improvement_pct:.1f}%)")
            
            # ═══════════════════════════════════════════════════════════
            # INICIAR MIGRAÇÃO DE OTIMIZAÇÃO
            # ═══════════════════════════════════════════════════════════
            
            try:
                origin_server = service.server  # Origem ESTÁ VIVA (otimização)
                
                # Decidir tipo de migração
                use_live_migration = _K8S_CONFIG['enable_live_migration']
                
                # ───────────────────────────────────────────────────────
                # LIVE MIGRATION (se habilitado)
                # ───────────────────────────────────────────────────────
                if use_live_migration:
                    print(f"[K8S_OPT] 🔄 Iniciando LIVE Migration para OTIMIZAÇÃO")
                    print(f"          Origem: {origin_server.id} (VIVA)")
                    print(f"          Destino: {best_server.id}")

                    # ❌ REMOVER mudança prematura
                    # service.server = best_server
                    # if service not in best_server.services:
                    #     best_server.services.append(service)

                    service._available = True
                    service._migration_reason = "delay_violation"

                    best_server.ongoing_migrations += 1
                    service.provision(target_server=best_server)

                    if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                        migration = service._Service__migrations[-1]
                        migration["migration_reason"] = "delay_violation"
                        migration["original_migration_reason"] = "delay_violation"
                        migration["is_proactive"] = True
                        migration["is_cold_migration"] = False
                        migration["origin"] = origin_server
                        migration["target"] = best_server
                        migration["relationships_created_by_algorithm"] = True

                    # ❌ REMOVER atualização manual de delay
                    # user.set_communication_path(app=app)
                    # new_delay = user._compute_delay(app=app, metric="latency")
                    # user.delays[app_id] = new_delay

                    print(f"[K8S_OPT] ✅ Live Migration iniciada (OTIMIZAÇÃO)")
                    increment_migration_counter("delay_violation", current_step, success=True)
                    migrations_triggered += 1
                
                # ───────────────────────────────────────────────────────
                # COLD MIGRATION (padrão)
                # ───────────────────────────────────────────────────────
                else:
                    print(f"[K8S_OPT] 🔄 Iniciando COLD Migration para OTIMIZAÇÃO")
                    print(f"          Origem: {origin_server.id}")
                    print(f"          Destino: {best_server.id}")
                    
                    # Marcar como indisponível
                    service._available = False
                    service._migration_reason = "delay_violation"
                    best_server.ongoing_migrations += 1
                    service.provision(target_server=best_server)

                    if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                        migration = service._Service__migrations[-1]
                        migration["migration_reason"] = "delay_violation"
                        migration["original_migration_reason"] = "delay_violation"
                        migration["is_cold_migration"] = True
                        migration["origin"] = origin_server
                        migration["target"] = best_server
                        migration["is_proactive"] = True
                        migration["optimization_metrics"] = {
                            "current_delay": current_delay,
                            "expected_delay": best_delay,
                            "improvement_ms": delay_reduction,
                            "improvement_pct": improvement_pct
                        }

                    # ❌ REMOVER atualização manual de delay
                    # user.set_communication_path(app=app)
                    # new_delay = user._compute_delay(app=app, metric="latency")
                    # user.delays[app_id] = new_delay

                    print(f"[K8S_OPT] ✅ Cold Migration iniciada (OTIMIZAÇÃO)")
                    increment_migration_counter("delay_violation", current_step, success=True)
                    migrations_triggered += 1
                    
            except Exception as e:
                print(f"[K8S_OPT] ❌ Erro ao migrar: {e}")
                import traceback
                traceback.print_exc()
                
                if best_server and hasattr(best_server, 'ongoing_migrations'):
                    best_server.ongoing_migrations -= 1
                increment_migration_counter("delay_violation", current_step, success=False)
    
    # ═══════════════════════════════════════════════════════════
    # RESUMO
    # ═══════════════════════════════════════════════════════════
    
    if migrations_triggered > 0:
        print(f"\n[K8S_OPT] ✅ {migrations_triggered} migrações de otimização iniciadas")
    else:
        print(f"\n[K8S_OPT] ℹ️ Nenhuma oportunidade de otimização encontrada")
    
    print(f"[K8S_OPT] 📊 Estatísticas:")
    print(f"          - Aplicações verificadas: {apps_checked}")
    print(f"          - Migrações disparadas: {migrations_triggered}")
    print(f"          - Limiar de melhoria: {IMPROVEMENT_THRESHOLD*100:.0f}%")
    
    print(f"[K8S_OPT] === FIM VERIFICAÇÃO DE OTIMIZAÇÃO ===\n")


def find_significantly_better_server(service, user, app, current_delay, improvement_threshold):
    """
    Encontra servidor com delay SIGNIFICATIVAMENTE MELHOR que atual.
    
    Args:
        service: Serviço a ser migrado
        user: Usuário acessando
        app: Aplicação
        current_delay: Delay atual em ms
        improvement_threshold: Melhoria mínima necessária (ex: 0.15 = 15%)
    
    Returns:
        (EdgeServer, float): Melhor servidor e seu delay, ou (None, inf)
    """
    best_server = None
    best_delay = float('inf')
    
    # Calcular delay mínimo necessário para migração
    max_acceptable_delay = current_delay * (1 - improvement_threshold)
    
    candidates_evaluated = 0
    
    for server in EdgeServer.all():
        # 1. Servidor deve estar disponível
        if server.status != "available":
            continue
        
        # 2. Servidor deve ter capacidade
        if not server.has_capacity_to_host(service):
            continue
        
        # 3. Pular servidor atual
        if server.id == service.server.id:
            continue
        
        candidates_evaluated += 1
        
        # 4. Calcular delay se serviço estivesse neste servidor
        original_server = service.server
        service.server = server
        
        user.set_communication_path(app=app)
        predicted_delay = user._compute_delay(app=app, metric="latency")
        
        # Restaurar servidor original
        service.server = original_server
        
        # 5. Verificar se melhoria é significativa
        if predicted_delay >= max_acceptable_delay:
            continue  # Melhoria insuficiente
        
        # 6. Escolher servidor com MENOR delay
        if predicted_delay < best_delay:
            best_delay = predicted_delay
            best_server = server
    
    if best_server:
        improvement = current_delay - best_delay
        improvement_pct = (improvement / current_delay) * 100
        
        print(f"[K8S_OPT] 🔍 Melhor servidor encontrado:")
        print(f"          Servidor: {best_server.id}")
        print(f"          Delay atual: {current_delay:.2f}ms")
        print(f"          Delay esperado: {best_delay:.2f}ms")
        print(f"          Melhoria: {improvement:.2f}ms ({improvement_pct:.1f}%)")
        print(f"          Candidatos avaliados: {candidates_evaluated}")
    
    return best_server, best_delay


def monitor_migration_health_and_recover(current_step):
    """
    Monitora saúde de origem e destino durante migrações em andamento.
    
    ✅ CORREÇÃO: Monitorar TODAS as migrações (não apenas server_failed).
    """
    print(f"\n[K8S_HEALTH] === MONITORAMENTO DE SAÚDE DAS MIGRAÇÕES - STEP {current_step} ===")
    
    services_recovered = 0
    services_failed = 0
    services_converted = 0
    
    for service in Service.all():
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            continue
        
        migration = service._Service__migrations[-1]
        
        # Pular migrações já finalizadas
        if migration.get("end") is not None:
            continue
        
        # ✅ CORREÇÃO: REMOVER filtro que exclui delay_violation
        # ANTES: if migration.get("migration_reason") != "server_failed": continue
        # DEPOIS: Processar TODAS as migrações
        
        origin = migration.get("origin")
        target = migration.get("target")

        if origin is None:
            continue 

        is_live = not migration.get("is_cold_migration", False)
        status = migration.get("status", "unknown")
        migration_reason = migration.get("migration_reason", "unknown")
        
        origin_alive = origin and origin.available
        target_alive = target and target.available
        
        # ═════════════════════════════════════════════════════════════
        # CENÁRIO 1: DESTINO FALHOU
        # ═════════════════════════════════════════════════════════════
        if not target_alive:
            # ✅ CORREÇÃO: Validar antes de acessar .id
            target_id = target.id if target else "None"
            origin_id = origin.id if origin else "None"
            
            print(f"[K8S_HEALTH] 🔴 Destino {target_id} FALHOU durante migração")
            print(f"              Service: {service.id}, Origin: {origin_id}")
            
            # Interromper migração atual
            migration["end"] = current_step
            migration["status"] = "interrupted"
            migration["interruption_reason"] = "target_server_failed"
            
            # Decrementar contador do destino
            if target and hasattr(target, 'ongoing_migrations'):
                target.ongoing_migrations = max(0, target.ongoing_migrations - 1)
            
            # ─────────────────────────────────────────────────────────
            # SUBCENÁRIO 1.1: DESTINO FALHA + ORIGEM VIVA (Live Migration)
            # ─────────────────────────────────────────────────────────
            if is_live and origin_alive:
                print(f"[K8S_HEALTH] ✅ Origem {origin_id} AINDA VIVA - Procurando novo destino")
                
                # Serviço volta a rodar na origem (se não estava)
                if service.server != origin:
                    service.server = origin
                    if service not in origin.services:
                        origin.services.append(service)
                
                service._available = True  # Garantir disponibilidade
                
                # Procurar novo destino
                app = service.application
                user = app.users[0] if app.users else None
                
                if user:
                    new_target = kubernetes_scheduler(service, user, app)
                    
                    if new_target and new_target.id != origin.id:
                        print(f"[K8S_HEALTH] 🔄 Novo destino encontrado: {new_target.id}")
                        print(f"              Reiniciando Live Migration...")
                        
                        service._available = True
                        # ✅ Definir razão ANTES
                        service._migration_reason = "server_failed"

                        new_target.ongoing_migrations += 1

                        service.provision(target_server=new_target)
                        
                        # Marcar nova migração
                        if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                            new_migration = service._Service__migrations[-1]
                            new_migration["relationships_created_by_algorithm"] = True
                            new_migration["migration_reason"] = "target_recovery"
                            new_migration["original_migration_reason"] = "server_failed"
                            new_migration["is_cold_migration"] = False
                            new_migration["origin"] = origin
                            new_migration["target"] = new_target
                            new_migration["is_retry_after_failure"] = True
                        
                        services_recovered += 1

                        _migration_counters["conversions"]["target_recovery"] += 1
                        _migration_counters["failures"]["target_failed"] += 1
                    else:
                        print(f"[K8S_HEALTH] ⚠️ Nenhum novo destino disponível - Mantendo na origem")
                        services_failed += 1
            
            # ─────────────────────────────────────────────────────────
            # SUBCENÁRIO 1.2: DESTINO FALHA + ORIGEM MORTA (Cold Migration)
            # ─────────────────────────────────────────────────────────
            elif not origin_alive:
                print(f"[K8S_HEALTH] 🔴 Origem {origin_id} TAMBÉM MORTA")
                print(f"              Service {service.id} ÓRFÃO - Procurando novo destino")
                
                service._available = False  # Indisponível (órfão)
                
                # Procurar novo destino para Cold Migration
                app = service.application
                user = app.users[0] if app.users else None
                
                if user:
                    new_target = kubernetes_scheduler(service, user, app)
                    
                    if new_target:
                        print(f"[K8S_HEALTH] 🔄 Novo destino encontrado: {new_target.id}")
                        print(f"              Iniciando Cold Migration de emergência...")
                        
                        service._available = False
                        # ✅ Definir razão ANTES
                        service._migration_reason = "server_failed"

                        new_target.ongoing_migrations += 1

                        service.provision(target_server=new_target)
                        
                        # Marcar nova migração
                        if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                            new_migration = service._Service__migrations[-1]
                            new_migration["migration_reason"] = "orphan_recovery"
                            new_migration["original_migration_reason"] = "server_failed"
                            new_migration["is_cold_migration"] = True
                            new_migration["origin"] = None  # Órfão (sem origem válida)
                            new_migration["target"] = new_target
                            new_migration["is_emergency_recovery"] = True
                        
                        services_recovered += 1

                        _migration_counters["conversions"]["orphan_recovery"] += 1
                        _migration_counters["failures"]["both_failed"] += 1
                    else:
                        print(f"[K8S_HEALTH] ❌ Nenhum destino disponível - Service fica Pending")
                        services_failed += 1
        
        # ═════════════════════════════════════════════════════════════
        # CENÁRIO 2: ORIGEM FALHOU (Live Migration em andamento)
        # ═════════════════════════════════════════════════════════════
        elif is_live and not origin_alive:
            # ✅ CORREÇÃO: Validar antes de acessar .id
            origin_id = origin.id if origin else "None"
            target_id = target.id if target else "None"
            
            print(f"[K8S_HEALTH] 🔴 Origem {origin_id} FALHOU durante Live Migration")
            print(f"              Service: {service.id}, Target: {target_id}")
            
            # ─────────────────────────────────────────────────────────
            # SUBCENÁRIO 2.1: ORIGEM FALHA + DESTINO VIVO
            # ─────────────────────────────────────────────────────────
            if target_alive:
                print(f"[K8S_HEALTH] ✅ Destino {target_id} AINDA VIVO - Convertendo para Cold Migration")
                
                # Converter Live → Cold Migration
                migration["is_cold_migration"] = True
                migration["converted_to_cold_at"] = current_step
                migration["conversion_reason"] = "origin_failed_during_live_migration"
                
                # Forçar mudança para destino (já está lá devido ao algoritmo)
                if service.server != target:
                    service.server = target
                    if service not in target.services:
                        target.services.append(service)
                
                # Marcar como indisponível (Cold Migration)
                service._available = False
                
                print(f"[K8S_HEALTH] 🔄 Live Migration convertida para Cold (origem falhou)")
                print(f"              Aguardando downloads no destino {target_id}...")
                
                services_converted += 1

                _migration_counters["conversions"]["live_to_cold"] += 1
                _migration_counters["failures"]["origin_failed"] += 1
            
            # ─────────────────────────────────────────────────────────
            # SUBCENÁRIO 2.2: AMBOS FALHARAM
            # ─────────────────────────────────────────────────────────
            else:
                print(f"[K8S_HEALTH] 🔴 AMBOS (origem E destino) FALHARAM!")
                print(f"              Service {service.id} PERDIDO - Procurando novo destino")
                
                # Interromper migração
                migration["end"] = current_step
                migration["status"] = "interrupted"
                migration["interruption_reason"] = "both_servers_failed"
                
                if target and hasattr(target, 'ongoing_migrations'):
                    target.ongoing_migrations = max(0, target.ongoing_migrations - 1)
                
                service._available = False
                
                # Procurar novo destino
                app = service.application
                user = app.users[0] if app.users else None
                
                if user:
                    new_target = kubernetes_scheduler(service, user, app)
                    
                    if new_target:
                        print(f"[K8S_HEALTH] 🔄 Novo destino encontrado: {new_target.id}")
                        print(f"              Iniciando Cold Migration de emergência...")
                        
                        service._available = False
                        # ✅ Definir razão ANTES
                        service._migration_reason = "server_failed"

                        new_target.ongoing_migrations += 1

                        service.provision(target_server=new_target)
                        
                        # Marcar nova migração
                        if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                            new_migration = service._Service__migrations[-1]
                            new_migration["migration_reason"] = "both_failed_recovery"
                            new_migration["original_migration_reason"] = "server_failed"
                            new_migration["is_cold_migration"] = True
                            new_migration["origin"] = None
                            new_migration["target"] = new_target
                            new_migration["is_emergency_recovery"] = True
                        
                        services_recovered += 1

                        _migration_counters["failures"]["no_recovery_possible"] += 1
                    else:
                        print(f"[K8S_HEALTH] ❌ Nenhum destino disponível")
                        services_failed += 1
    
    # ═════════════════════════════════════════════════════════════
    # RESUMO
    # ═════════════════════════════════════════════════════════════
    if services_recovered > 0 or services_failed > 0 or services_converted > 0:
        print(f"\n[K8S_HEALTH] Resumo do monitoramento:")
        print(f"              - Services recuperados: {services_recovered}")
        print(f"              - Live → Cold conversões: {services_converted}")
        print(f"              - Services que falharam: {services_failed}")
    
    print(f"[K8S_HEALTH] === FIM MONITORAMENTO DE SAÚDE ===\n")


# ...existing code...

def k8s_validate_predictions(current_step):
    """
    Valida previsões de falha feitas anteriormente (espelho do TrustEdge).
    """
    global _k8s_prediction_quality
    
    if not _K8S_CONFIG.get('enable_failure_prediction', False):
        return
    
    # Log periódico de status
    if current_step % 100 == 0:
        pending = sum(
            1 for item in _k8s_prediction_quality["proactive_migrations"]
            if not item.get("validated", False)
        )
        if pending > 0:
            tp = _k8s_prediction_quality["true_positives"]
            fp = _k8s_prediction_quality["false_positives"]
            print(f"[K8S_VALIDATE] Step {current_step}: {pending} previsões pendentes "
                  f"(TP:{tp} FP:{fp})")
    
    validations_done = 0
    
    for item in _k8s_prediction_quality["proactive_migrations"]:
        # Pular já validadas
        if item.get("validated", False):
            continue
        
        server_id = item.get("server_id")
        deadline = item.get("deadline")
        step_predicted = item.get("step")
        
        # Validar apenas após o prazo
        if current_step < deadline:
            continue
        
        # ✅ CORREÇÃO: Sintaxe correta do EdgeSimPy
        server = EdgeServer.find_by(attribute_name="id", attribute_value=server_id)
        
        if not server:
            # Servidor não existe mais (caso raro)
            item["validated"] = True
            item["outcome"] = "server_not_found"
            continue
        
        # ═══════════════════════════════════════════════════════════
        # VERIFICAR SE SERVIDOR FALHOU NO PRAZO
        # ═══════════════════════════════════════════════════════════
        
        # Verificar histórico de falhas entre step_predicted e deadline
        server_failed_in_window = False
        
        if hasattr(server, 'failure_model') and hasattr(server.failure_model, 'failure_history'):
            for failure in server.failure_model.failure_history:
                failure_start = failure.get("failure_starts_at")
                
                # Falha ocorreu dentro da janela de predição?
                if step_predicted <= failure_start <= deadline:
                    server_failed_in_window = True
                    break
        
        # ═══════════════════════════════════════════════════════════
        # CLASSIFICAR: TP ou FP
        # ═══════════════════════════════════════════════════════════
        
        if server_failed_in_window:
            # TRUE POSITIVE: Previmos falha e ela ocorreu
            item["outcome"] = "server_failed_correctly_predicted"
            item["validated"] = True
            _k8s_prediction_quality["true_positives"] += 1
            validations_done += 1
            
            print(f"[K8S_VALIDATE] ✅ TP: Server {server_id} falhou conforme previsto "
                  f"(step {step_predicted} → falha detectada)")
        
        else:
            # FALSE POSITIVE: Previmos falha mas não ocorreu
            item["outcome"] = "server_survived_validation_window"
            item["validated"] = True
            _k8s_prediction_quality["false_positives"] += 1
            validations_done += 1
            
            print(f"[K8S_VALIDATE] ❌ FP: Server {server_id} sobreviveu "
                  f"(step {step_predicted} → deadline {deadline})")
    
    if validations_done > 0:
        tp = _k8s_prediction_quality["true_positives"]
        fp = _k8s_prediction_quality["false_positives"]
        print(f"[K8S_VALIDATE] {validations_done} validações concluídas. Total: TP={tp}, FP={fp}")