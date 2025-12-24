# Importing EdgeSimPy components
from edge_sim_py import *

# Importing native Python modules/packages
from json import dumps
import math
import operator
from datetime import datetime

# Importing helper functions
from simulator.helper_functions import *

# Importing EdgeSimPy extensions
from simulator.extensions import *

# Importing from trust_edge_v3 for shared functions
from .trust_edge_v3 import check_and_deprovision_inactive_services

"""
KUBERNETES STANDARD ALGORITHM FOR EDGE COMPUTING
Implements authentic Kubernetes behavior:
- Resource-based scheduling (CPU, RAM) - NO latency consideration
- QoS based on requests/limits (simulated via resource ratios)
- NO proactive migration
- NO automatic rebalancing
- Reactive pod recreation on node failures only
"""

# ============================================================================
# GLOBAL MIGRATION COUNTERS
# ============================================================================

_migration_counters = {
    "total": 0,
    "by_reason": {
        "server_failed": 0,
        "delay_violation": 0,
        "low_reliability": 0
    },
    "by_step": {},
    "successful": 0,
    "failed": 0
}

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
        "failed": 0
    }

def increment_migration_counter(reason, current_step, success=True):
    global _migration_counters
    _migration_counters["total"] += 1
    
    if reason in _migration_counters["by_reason"]:
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
    print(f"RESUMO DE RECRIAÇÕES DE PODS (Kubernetes Standard)")
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
    Implementa scheduler PADRÃO do Kubernetes (kube-scheduler):
    
    1. Filtering Phase (Predicates):
       - PodFitsResources: Node tem recursos suficientes
       - NodeCondition: Node está Ready
       
    2. Scoring Phase (Priorities):
       - NodeResourcesLeastAllocated (peso padrão: 1)
       - NodeResourcesBalancedAllocation (peso padrão: 1)
       - ImageLocality (peso padrão: 1)
       
    NOTA: Kubernetes padrão NÃO considera latência/localidade de rede!
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
    Scoring Phase - Priorities do Kubernetes PADRÃO:
    
    Plugins ativos por padrão (todos com peso 1):
    1. NodeResourcesLeastAllocated: Favorece nodes com MAIS recursos livres
    2. NodeResourcesBalancedAllocation: Favorece nodes com uso balanceado
    3. ImageLocality: Favorece nodes que já têm as imagens
    
    IMPORTANTE: Kubernetes padrão NÃO considera latência ou localização!
    Para edge computing, seria necessário custom scheduler.
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
        
        # 3. ImageLocality (peso: 1, normalizado 0-10)
        # Usar função nativa do EdgeSimPy para calcular camadas não-cached
        if hasattr(service, 'image_digest'):
            service_image = ContainerImage.find_by(attribute_name="digest", attribute_value=service.image_digest)
            total_layers = len(service_image.layers_digests) if service_image and hasattr(service_image, 'layers_digests') else 0
            uncached_layers = server._get_uncached_layers(service=service)
            cached_layers = total_layers - len(uncached_layers)
            if total_layers > 0:
                image_score = (cached_layers / total_layers) * 10
            else:
                image_score = 0
        else:
            image_score = 0
        
        image_score = min(image_score, 10)  # Garantir 0-10
        total_score += image_score
        
        # Score final: soma direta (0-30), normalizada para 0-100
        normalized_score = (total_score / 30) * 100
        
        scored_nodes.append({
            "server": server,
            "score": normalized_score,
            "least_allocated": least_allocated_score,
            "balanced": balanced_score,
            "image_locality": image_score
        })
    
    return scored_nodes

# ============================================================================
# MAIN ALGORITHM
# ============================================================================

def kubernetes_inspired(parameters: dict = {}):
    """
    Algoritmo que simula Kubernetes PADRÃO.
    
    COMPORTAMENTO REAL DO KUBERNETES:
    1. Scheduling acontece APENAS na criação do pod
    2. NÃO há rebalanceamento automático de pods
    3. NÃO há migração proativa por performance
    4. Migração (recreação) ocorre APENAS em:
       - Node failure (NotReady/Unknown)
       - Resource pressure eviction
       - Manual eviction/drain
    
    LIMITAÇÕES RECONHECIDAS:
    - Não considera latência de rede
    - Não otimiza para edge computing
    - Pode resultar em distribuição não-ideal
    """
    current_step = parameters.get("current_step")

    if current_step == 0:
        reset_migration_counters()
        print("[K8S] Kubernetes Standard Scheduler inicializado")
        print("[K8S] AVISO: Sem migração proativa ou rebalanceamento automático")

        # Log dataset overview for validation
        from simulator.helper_functions import show_scenario_overview
        show_scenario_overview()  # From helper_functions.py
        print("[K8S] Dataset validado: focando em resource-based scheduling.")
    
    # 1. DESPROVISIONAMENTO DE SERVIÇOS INATIVOS
    check_and_deprovision_inactive_services(current_step)

    # 2. ATUALIZAR DELAYS (métrica, não influencia decisões)
    update_application_delays(current_step)

    # 3. MIGRAÇÃO REATIVA (apenas falhas de node)
    # Kubernetes NÃO migra por performance/latência
    reactive_pod_recreation(current_step)

    # 4. PROVISIONAMENTO DE NOVAS REQUISIÇÕES
    # Scheduling ocorre APENAS aqui, nunca depois
    provision_new_requests(current_step)

    # 5. ATUALIZAR DOWNTIME PERCEBIDO
    update_user_perceived_downtime_for_current_step(current_step)

    # 6. COLETA DE MÉTRICAS
    collect_sla_violations_for_current_step()
    collect_infrastructure_metrics_for_current_step()

    # 7. RELATÓRIO FINAL
    if parameters.get("time_steps") == current_step:
        print_migration_summary()

# ============================================================================
# REACTIVE POD RECREATION (não é migração, é recreação)
# ============================================================================

def reactive_pod_recreation(current_step):
    """
    Pod Recreation - Comportamento REAL do Kubernetes:
    
    Quando um node falha:
    1. Node Controller marca node como NotReady
    2. Após timeout (default: 5min), pods são marcados para deletion
    3. ReplicaSet/Deployment cria NOVOS pods em nodes saudáveis
    4. Pods antigos são DELETADOS (não migrados!)
    
    IMPORTANTE: Isto NÃO é live migration!
    - Pod antigo é terminado
    - Novo pod tem novo UID
    - Estado em disco é perdido (exceto PersistentVolumes)
    """
    print(f"\n[K8S] === VERIFICAÇÃO DE NODE FAILURES - STEP {current_step} ===")
    
    pods_to_recreate = []
    
    for user in User.all():
        active_applications = get_active_applications_with_remaining_time(user, current_step)
        
        for app_info in active_applications:
            app = app_info["application"]
            service = app.services[0]
            
            # Verificar se node falhou
            if not service.server or service.server.status != "available":
                qos_class = classify_qos(service)
                
                pods_to_recreate.append({
                    "service": service,
                    "application": app,
                    "user": user,
                    "qos_class": qos_class,
                    "qos_priority": get_qos_priority(qos_class)
                })
    
    if not pods_to_recreate:
        print(f"[K8S] Nenhum pod precisa ser recriado")
        return
    
    # Ordenar por QoS (Guaranteed tem prioridade)
    pods_to_recreate.sort(key=lambda x: x["qos_priority"], reverse=True)
    
    print(f"[K8S] {len(pods_to_recreate)} pods precisam ser recriados")
    
    for item in pods_to_recreate:
        service = item["service"]
        app = item["application"]
        user = item["user"]
        qos_class = item["qos_class"]
        
        # Simular eviction delay (e.g., 5min = 300 steps, mas ajustar para simulação)
        eviction_delay = 5  # steps
        if current_step - item.get("failure_detected_at", 0) < eviction_delay:
            continue  # Ainda não evitou

        print(f"\n[K8S] Recriando pod {service.id} (QoS: {qos_class})")
        print(f"      Node anterior: {'FAILED' if not service.server else service.server.id}")
        
        # Usar scheduler para encontrar novo node
        target_server = kubernetes_scheduler(service, user, app)
        
        if target_server:
            try:
                # Simular terminação do pod antigo
                if service.server:
                    print(f"[K8S] Terminando pod antigo no node {service.server.id}")
                
                # Criar novo pod no novo node
                target_server.ongoing_migrations += 1
                
                service.provision(target_server=target_server)
                
                user.set_communication_path(app=app)
                new_delay = user._compute_delay(app=app, metric="latency")
                user.delays[str(app.id)] = new_delay
                
                print(f"[K8S] ✓ Novo pod criado no node {target_server.id}")
                print(f"      Delay resultante: {new_delay:.2f}ms")
                increment_migration_counter("server_failed", current_step, success=True)
                
            except Exception as e:
                print(f"[K8S] ✗ Erro ao recriar pod: {e}")
                target_server.ongoing_migrations -= 1
                increment_migration_counter("server_failed", current_step, success=False)
        else:
            print(f"[K8S] ✗ Nenhum node disponível para recriar pod")
            increment_migration_counter("server_failed", current_step, success=False)
    
    print(f"[K8S] === FIM VERIFICAÇÃO DE NODE FAILURES ===\n")

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
    Atualiza delays (apenas para métricas).
    
    IMPORTANTE: No Kubernetes real, delays NÃO influenciam decisões!
    """
    for user in User.all():
        for app in user.applications:
            service = app.services[0]
            
            if is_making_request(user, current_step):
                continue
            
            if is_user_accessing_application(user, app, current_step):
                if service.server and service.server.status == "available":
                    user.set_communication_path(app=app)
                    new_delay = user._compute_delay(app=app, metric="latency")
                    user.delays[str(app.id)] = new_delay
                else:
                    user.delays[str(app.id)] = float('inf')

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