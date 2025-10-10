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

"""TRUST EDGE ALGORITHM V3 - WITH PROACTIVE MIGRATION AND WAITING QUEUE"""

# ============================================================================
# GLOBAL WAITING QUEUE FOR UNPROVISIONED APPLICATIONS
# ============================================================================

_waiting_queue = []

def get_waiting_queue():
    """Retorna a fila de espera global."""
    return _waiting_queue

def add_to_waiting_queue(user, application, service, priority_score=0):
    """Adiciona uma aplicação à fila de espera."""
    # Verificar se a aplicação já está na fila
    for item in _waiting_queue:
        if item["application"].id == application.id:
            print(f"[LOG] Aplicação {application.id} já está na fila de espera.")
            return
        
    waiting_item = {
        "user": user,
        "application": application,
        "service": service,
        "priority_score": priority_score,
        "queued_at_step": user.model.schedule.steps,
        "delay_sla": user.delay_slas[str(application.id)]
    }
    
    _waiting_queue.append(waiting_item)
    print(f"[LOG] Aplicação {application.id} adicionada à fila de espera (Prioridade: {priority_score:.4f})")

def remove_from_waiting_queue(application_id):
    """Remove uma aplicação da fila de espera."""
    global _waiting_queue
    _waiting_queue = [item for item in _waiting_queue if item["application"].id != application_id]

# ============================================================================
# MAIN ALGORITHM
# ============================================================================

def trust_edge_v3(parameters: dict = {}):
    """Algoritmo principal que implementa a lógica do TrustEdge V3 (com migração proativa).

    Executa em ordem:
    1. Processa fila de espera (aplicações que estão desprovisionadas e aguardando)
    2. Monitora e migra serviços (aplicações provisionadas)
    3. Provisiona novas requisições
    4. Coleta métricas
    
    Args:
        parameters (dict): Parâmetros da simulação.
    """
    current_step = parameters.get("current_step") - 1
    
    # 1. PROCESSAR FILA DE ESPERA
    process_waiting_queue(current_step)
    
    # 2. MONITORAMENTO E MIGRAÇÃO
    monitor_and_migrate_services(parameters)
    
    # 3. PROVISIONAMENTO DE NOVAS REQUISIÇÕES
    provision_new_requests(current_step)

    # 4. COLETA DE MÉTRICAS
    collect_sla_violations_for_current_step()
    collect_infrastructure_metrics_for_current_step()
    #display_simulation_metrics(simulation_parameters=parameters)

# ============================================================================
# WAITING QUEUE PROCESSING
# ============================================================================

def process_waiting_queue(current_step):
    """Processa a fila de espera tentando provisionar aplicações em servidores disponíveis."""
    if not _waiting_queue:
        print(f"\n[LOG] === FILA DE ESPERA VAZIA - STEP {current_step} ===")
        return
        
    print(f"\n[LOG] === PROCESSANDO FILA DE ESPERA - STEP {current_step} ===")
    print(f"[LOG] {len(_waiting_queue)} aplicações na fila de espera")
    
    # Ordenar fila por prioridade (decrescente) e proximidade do SLA
    _waiting_queue.sort(key=lambda item: (
        -item["priority_score"],  # Maior prioridade primeiro
        get_delay_urgency(item)   # Mais próximo da violação primeiro
    ))
    
    provisioned_items = []
    
    for waiting_item in _waiting_queue:
        user = waiting_item["user"]
        app = waiting_item["application"]
        service = waiting_item["service"]
        queued_step = waiting_item["queued_at_step"]
        
        # Verificar se o usuário ainda está acessando
        if not is_user_accessing_application(user, app, current_step):
            print(f"[LOG] Usuário {user.id} não está mais acessando aplicação {app.id} - removendo da fila")
            provisioned_items.append(waiting_item)
            continue
        
        remaining_time = get_remaining_access_time(user, app, current_step)
        if remaining_time <= 0:
            print(f"[LOG] Tempo de acesso da aplicação {app.id} expirou - removendo da fila")
            provisioned_items.append(waiting_item)
            continue
            
        print(f"\n[LOG] Tentando provisionar aplicação {app.id} da fila:")
        print(f"      Usuário: {user.id}")
        print(f"      Tempo na fila: {current_step - queued_step} steps")
        print(f"      Tempo restante: {remaining_time} steps")
        
        # Tentar provisionar
        if try_provision_service(user, app, service):
            provisioned_items.append(waiting_item)
        else:
            print(f"[LOG] Aplicação {app.id} ainda não pode ser provisionada")
    
    # Remover itens processados da fila
    for item in provisioned_items:
        _waiting_queue.remove(item)
    
    print(f"[LOG] {len(provisioned_items)} aplicações processadas")
    print(f"[LOG] {len(_waiting_queue)} aplicações restantes na fila")
    print(f"[LOG] === FIM PROCESSAMENTO FILA DE ESPERA ===\n")

def get_delay_urgency(waiting_item):
    """Calcula urgência baseada na proximidade da violação de SLA."""
    user = waiting_item["user"]
    app = waiting_item["application"]
    current_delay = user.delays[str(app.id)] if user.delays[str(app.id)] is not None else 0
    delay_sla = user.delay_slas[str(app.id)]
    return delay_sla - current_delay  # Quanto menor, mais urgente

# ============================================================================
# SERVICE MONITORING AND MIGRATION
# ============================================================================

def monitor_and_migrate_services(parameters: dict = {}):
    """Monitora servidores e migra serviços quando necessário."""
    current_step = parameters.get("current_step") - 1
    reliability_threshold = parameters.get("reliability_threshold", 70.0)
    delay_threshold = parameters.get("delay_threshold", 1.0)
    
    print(f"\n[LOG] === MONITORAMENTO E MIGRAÇÃO - STEP {current_step} ===")
    
    # 1. Verificar migrações em andamento
    check_ongoing_migrations(current_step)
    
    # 2. Identificar novos serviços para migração

    services_to_migrate = identify_services_for_migration(current_step, reliability_threshold, delay_threshold)

    # 3. Processar fila de migração
    process_migration_queue(services_to_migrate, current_step)
    
    print(f"[LOG] === FIM MONITORAMENTO E MIGRAÇÃO ===\n")

def check_ongoing_migrations(current_step):
    """Verifica e atualiza migrações em andamento."""
    print(f"[LOG] Verificando migrações em andamento...")
    
    migrations_in_progress = 0
    for service in Service.all():
        if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
            migration = service._Service__migrations[-1]
            
            if migration["end"] is None:  # Migração ativa
                migrations_in_progress += 1
                print(f"[LOG] Serviço {service.id} em migração - Status: {migration['status']}")
                
                # Atualizar contadores de tempo
                if migration["status"] == "waiting":
                    migration["waiting_time"] = migration.get("waiting_time", 0) + 1
                elif migration["status"] == "pulling_layers":
                    migration["pulling_layers_time"] = migration.get("pulling_layers_time", 0) + 1
                elif migration["status"] == "migrating_service_state":
                    migration["migrating_service_state_time"] = migration.get("migrating_service_state_time", 0) + 1
    
    if migrations_in_progress == 0:
        print(f"[LOG] Nenhuma migração em andamento")
    else:
        print(f"[LOG] {migrations_in_progress} migrações em andamento")

def identify_services_for_migration(current_step, reliability_threshold, delay_threshold):
    """Identifica serviços que precisam ser migrados."""
    services_to_migrate = []
    
    for user in User.all():
        active_applications = get_active_applications_with_remaining_time(user, current_step)
        
        for app_info in active_applications:
            app = app_info["application"]
            service = app.services[0]
            server = service.server

            # Só migrar se estiver PROVISIONADO
            if not server or service.being_provisioned:
                continue
            
            # Verificar se já está na fila de espera (não deveria migrar)
            if is_application_in_waiting_queue(app.id):
                continue
            
            # Avaliar critérios de migração
            migration_criteria = evaluate_migration_criteria(
                service, server, user, app, app_info["remaining_time"],
                reliability_threshold, delay_threshold, current_step
            )
            
            if migration_criteria["needs_migration"]:
                services_to_migrate.append({
                    "service": service,
                    "application": app,
                    "user": user,
                    "current_server": server,
                    "reason": migration_criteria["reason"],
                    "priority": migration_criteria["priority"],
                    "remaining_access_time": app_info["remaining_time"],
                    "criteria_data": migration_criteria
                })
    
    return services_to_migrate

def evaluate_migration_criteria(service, server, user, app, remaining_time, 
                               reliability_threshold, delay_threshold, current_step):
    """Avalia todos os critérios para migração de um serviço."""
    
    # 1. Servidor em falha (prioridade máxima)
    if is_ongoing_failure(server, current_step):
        return {
            "needs_migration": True,
            "reason": "server_failed",
            "priority": 1
        }
    
    # 2. Violação de delay
    current_delay = user.delays[str(app.id)] if user.delays[str(app.id)] is not None else 0
    delay_sla = user.delay_slas[str(app.id)]
    delay_limit = delay_sla * delay_threshold
    
    if current_delay > delay_limit:
        return {
            "needs_migration": True,
            "reason": "delay_violation",
            "priority": 2,
            "delay_violation_ratio": current_delay / delay_sla
        }
    
    # 3. Baixa confiabilidade condicional
    conditional_reliability = get_server_conditional_reliability(server, remaining_time)
    if conditional_reliability < reliability_threshold:
        return {
            "needs_migration": True,
            "reason": "low_reliability", 
            "priority": 3,
            "conditional_reliability": conditional_reliability
        }
    
    return {"needs_migration": False}

def is_application_in_waiting_queue(application_id):
    """Verifica se uma aplicação já está na fila de espera."""
    return any(item["application"].id == application_id for item in _waiting_queue)

def process_migration_queue(services_to_migrate, current_step):
    """Processa fila de serviços que precisam ser migrados."""
    if not services_to_migrate:
        print(f"[LOG] Nenhum serviço precisa ser migrado")
        return
    
    # Ordenar por prioridade e urgência
    services_to_migrate.sort(key=lambda s: (
        s["priority"],
        -s["criteria_data"].get("delay_violation_ratio", 0),
        s["criteria_data"].get("conditional_reliability", 100)
    ))
    
    print(f"[LOG] Processando {len(services_to_migrate)} serviços para migração")
    
    for service_metadata in services_to_migrate:
        service = service_metadata["service"]
        app = service_metadata["application"]
        user = service_metadata["user"]
        current_server = service_metadata["current_server"]
        reason = service_metadata["reason"]
        
        print(f"\n[LOG] Migrando serviço {service.id} - Razão: {reason}")
        print(f"[LOG] Servidor atual: {current_server.id} (Status: {current_server.status})")

        # Encontrar servidor de destino
        target_server = find_migration_target(user, service, current_server, reason)
        
        if target_server:
            initiate_service_migration(service, target_server, reason, current_step)
        else:
            if current_server.status == "available":
                print(f"[LOG] Sem servidor disponível - mantendo no servidor atual {current_server.id}")
            else:
                # Servidor falhou E não há alternativa - DESPROVISIONAMENTO
                print(f"[LOG] Servidor {current_server.id} falhou e sem alternativas - desprovisionando serviço")
               
               # Adicionar à fila de espera com alta prioridade (falha de servidor)
                priority_score = 999.0  # Prioridade máxima para falhas de servidor
                add_to_waiting_queue(user, app, service, priority_score)

def find_migration_target(user, service, current_server, migration_reason):
    """Encontra o melhor servidor de destino para migração."""
    available_servers = [s for s in EdgeServer.all() 
                        if s.status == "available" 
                        and s != current_server 
                        and s.has_capacity_to_host(service)]
    
    if not available_servers:
        return None
    
    # Avaliar candidatos com foco em cache e proximidade
    migration_candidates = evaluate_migration_candidates(
        user, service, current_server, available_servers
    )
    
    return migration_candidates[0]["server"] if migration_candidates else None

def evaluate_migration_candidates(user, service, current_server, available_servers):
    """Avalia candidatos para migração priorizando cache e SLA."""
    app_delay = user.delays[str(service.application.id)] if user.delays[str(service.application.id)] is not None else 0
    delay_sla = user.delay_slas[str(service.application.id)]
    
    # Obter informações da imagem para análise de cache
    service_image = ContainerImage.find_by(attribute_name="digest", attribute_value=service.image_digest)
    service_layers = [ContainerLayer.find_by(attribute_name="digest", attribute_value=digest) 
                     for digest in service_image.layers_digests]
    
    candidates = []
    
    for edge_server in available_servers:
        # Calcular delay e violação SLA
        additional_delay = calculate_path_delay(
            origin_network_switch=user.base_station.network_switch,
            target_network_switch=edge_server.network_switch
        )
        overall_delay = app_delay + additional_delay
        violates_delay_sla = overall_delay > delay_sla
        
        # Calcular vantagem de cache
        cached_layers_count = sum(1 for service_layer in service_layers
                                 for cached_layer in edge_server.container_layers
                                 if cached_layer.digest == service_layer.digest)
        cache_advantage = cached_layers_count / len(service_layers) if service_layers else 0
        
        # Calcular outros fatores
        trust_cost = get_server_trust_cost(edge_server)
        migration_distance = calculate_path_delay(
            origin_network_switch=current_server.network_switch,
            target_network_switch=edge_server.network_switch
        )
        
        candidates.append({
            "server": edge_server,
            "violates_delay_sla": violates_delay_sla,
            "cache_advantage": cache_advantage,
            "trust_cost": trust_cost,
            "migration_distance": migration_distance,
        })
    
    # Ordenar por adequação para migração
    candidates.sort(key=lambda s: (
        s["violates_delay_sla"],     # Sem violação primeiro
        -s["cache_advantage"],       # Maior cache primeiro
        s["trust_cost"],             # Menor risco primeiro
        s["migration_distance"],     # Menor distância primeiro
    ))
    
    return candidates

def initiate_service_migration(service, target_server, reason, current_step):
    """Inicia migração de serviço usando infraestrutura EdgeSimPy."""
    print(f"[LOG] ✓ Iniciando migração {service.server.id} → {target_server.id}")
    
    app = service.application
    user = app.users[0]
    try:
        # Incrementar contadores de migração
        if service.server:
            service.server.ongoing_migrations += 1
        target_server.ongoing_migrations += 1
        
        provision(user=user, application=app, service=service, edge_server=target_server)
        
        # Adicionar metadados sobre a migração
        if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
            migration = service._Service__migrations[-1]
            migration["migration_reason"] = reason
            migration["triggered_at_step"] = current_step
            
            print(f"[LOG] Migração iniciada - Status: {migration['status']}")
        
    except Exception as e:
        print(f"[LOG] ✗ Erro ao iniciar migração: {e}")
        # Reverter contadores em caso de erro
        if service.server:
            service.server.ongoing_migrations -= 1
        target_server.ongoing_migrations -= 1

# ============================================================================
# NEW REQUEST PROVISIONING
# ============================================================================

def provision_new_requests(current_step):
    """Provisiona novas requisições de aplicações."""
    print(f"\n[LOG] === PROVISIONAMENTO DE NOVAS REQUISIÇÕES - STEP {current_step} ===")
    
    # Coletar aplicações com novas requisições
    apps_metadata = collect_new_request_metadata(current_step)
    
    if apps_metadata:
        print(f"[LOG] {len(apps_metadata)} aplicações com novas requisições")
        
        # Ordenar por prioridade
        apps_metadata = sort_applications_by_priority(apps_metadata)
        
        # Processar cada aplicação
        for app_metadata in apps_metadata:
            process_application_request(app_metadata, apps_metadata)
    else:
        print(f"[LOG] Nenhuma nova requisição no step {current_step}")
    
    print(f"[LOG] === FIM PROVISIONAMENTO DE NOVAS REQUISIÇÕES ===\n")

def collect_new_request_metadata(current_step):
    """Coleta metadados de aplicações com novas requisições."""
    apps_metadata = []
    
    for user in User.all():
        if is_making_request(user, current_step):
            for app in user.applications:
                app_attrs = {
                    "object": app,
                    "delay_sla": app.users[0].delay_slas[str(app.id)],
                    "delay_score": get_application_delay_score(app),
                    "intensity_score": get_application_access_intensity_score(app),
                    "demand_resource": get_normalized_demand(app.services[0]),
                }
                apps_metadata.append(app_attrs)
    
    return apps_metadata

def sort_applications_by_priority(apps_metadata):
    """Ordena aplicações por prioridade usando normalização."""
    min_and_max_app = find_minimum_and_maximum(metadata=apps_metadata)
    
    return sorted(
        apps_metadata, 
        key=lambda app: (
            get_norm(metadata=app, attr_name="delay_score", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]) +
            get_norm(metadata=app, attr_name="intensity_score", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]) +
            (1 - get_norm(metadata=app, attr_name="demand_resource", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]))
        ), 
        reverse=True
    )

def process_application_request(app_metadata, all_apps_metadata):
    """Processa requisição de uma aplicação específica."""
    app = app_metadata["object"]
    user = app.users[0]
    service = app.services[0]
    
    print(f"\n[LOG] Processando aplicação {app.id}:")
    print(f"      Delay Score: {app_metadata['delay_score']:.4f}")
    print(f"      SLA: {app_metadata['delay_sla']}")
    
    # Verificar se já está provisionado
    if service.server:
        print(f"[LOG] Serviço já hospedado no servidor {service.server.id}")
        return
    
    # Verificar se já está na fila de espera
    if is_application_in_waiting_queue(app.id):
        print(f"[LOG] Aplicação {app.id} já está na fila de espera")
        return
    
    # Tentar provisionar
    if not try_provision_service(user, app, service):
        # Adicionar à fila de espera se falhou
        min_and_max_app = find_minimum_and_maximum(metadata=all_apps_metadata)
        priority_score = calculate_application_priority_score(app_metadata, min_and_max_app)
        add_to_waiting_queue(user, app, service, priority_score)

def try_provision_service(user, app, service):
    """Tenta provisionar um serviço, retorna True se bem-sucedido."""
    edge_servers = get_host_candidates(user=user, service=service)
    
    if not edge_servers:
        print(f"[LOG] Nenhum servidor disponível para aplicação {app.id}")
        return False
    
    # Ordenar servidores candidatos
    edge_servers = sort_host_candidates(edge_servers)
    
    # Tentar provisionar no melhor candidato disponível
    for edge_server_metadata in edge_servers:
        edge_server = edge_server_metadata["object"]
        
        if edge_server.has_capacity_to_host(service):
            print(f"[LOG] ✓ Provisionando aplicação {app.id} no servidor {edge_server.id}")
            provision(user=user, application=app, service=service, edge_server=edge_server)
            return True
    
    print(f"[LOG] ✗ Servidores sem capacidade para aplicação {app.id}")
    return False

def sort_host_candidates(edge_servers):
    """Ordena candidatos por adequação para hospedagem."""
    min_and_max = find_minimum_and_maximum(metadata=edge_servers)
    
    return sorted(
        edge_servers,
        key=lambda s: (
            s["sla_violations"],
            get_norm(metadata=s, attr_name="trust_cost", min=min_and_max["minimum"], max=min_and_max["maximum"]) +
            get_norm(metadata=s, attr_name="amount_of_uncached_layers", min=min_and_max["minimum"], max=min_and_max["maximum"]) +
            get_norm(metadata=s, attr_name="overall_delay", min=min_and_max["minimum"], max=min_and_max["maximum"]),
        ),
    )

def calculate_application_priority_score(app_metadata, min_and_max_app):
    """Calcula score de prioridade de uma aplicação."""
    return (
        get_norm(metadata=app_metadata, attr_name="delay_score", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]) +
        get_norm(metadata=app_metadata, attr_name="intensity_score", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]) +
        (1 - get_norm(metadata=app_metadata, attr_name="demand_resource", min=min_and_max_app["minimum"], max=min_and_max_app["maximum"]))
    )

# ============================================================================
# USER ACCESS PATTERN FUNCTIONS
# ============================================================================

def get_remaining_access_time(user, application, current_step):
    """Calcula tempo restante de acesso em steps."""
    app_id = str(application.id)
    
    if app_id not in user.access_patterns:
        return 0
    
    access_pattern = user.access_patterns[app_id]
    if not access_pattern.history:
        return 0
    
    last_access = access_pattern.history[-1]
    
    if not (last_access["start"] <= current_step <= last_access["end"]):
        return 0
    
    return max(0, last_access["end"] - current_step)

def get_active_applications_with_remaining_time(user, current_step):
    """Retorna aplicações ativas com informações de tempo."""
    active_applications = []
    
    for application in user.applications:
        if is_user_accessing_application(user, application, current_step):
            remaining_time = get_remaining_access_time(user, application, current_step)
            
            app_id = str(application.id)
            last_access = user.access_patterns[app_id].history[-1]
            
            active_applications.append({
                "application": application,
                "remaining_time": remaining_time,
                "total_duration": last_access["duration"],
                "access_start": last_access["start"],
                "access_end": last_access["end"]
            })
    
    return active_applications

# ============================================================================
# RELIABILITY AND TRUST METRICS
# ============================================================================

def get_server_total_failures(server):
    """Retorna número total de falhas de um servidor."""
    return len(server.failure_model.failure_history)

def get_server_mttr(server):
    """Calcula Mean Time To Repair (MTTR) do servidor."""
    history = server.failure_model.failure_history
    repair_times = []
    
    for failure_occurrence in history:
        repair_times.append(failure_occurrence["becomes_available_at"] - failure_occurrence["failure_starts_at"])
    
    return sum(repair_times) / len(repair_times) if repair_times else 0

def get_server_downtime_history(server):
    """Calcula downtime total do histórico completo."""
    total_downtime = 0
    
    for failure_occurrence in server.failure_model.failure_history:
        failure_start = failure_occurrence["failure_starts_at"]
        failure_end = failure_occurrence["becomes_available_at"]
        total_downtime += failure_end - failure_start
    
    return total_downtime

def get_server_uptime_history(server):
    """Calcula uptime total do histórico completo."""
    if not server.failure_model.failure_history:
        return float("inf")
    
    total_time_span = abs(getattr(server.failure_model, 'initial_failure_time_step') - (server.model.schedule.steps + 1)) + 1
    total_downtime = get_server_downtime_history(server=server)
    
    return total_time_span - total_downtime

def get_server_downtime_simulation(server):
    """Calcula downtime durante a simulação."""
    return sum(1 for available in server.available_history if available is False)

def get_server_uptime_simulation(server):
    """Calcula uptime durante a simulação."""
    return sum(1 for available in server.available_history if available is True)

def get_server_mtbf(server):
    """Calcula Mean Time Between Failures (MTBF)."""
    number_of_failures = len(server.failure_model.failure_history)
    
    if number_of_failures == 0:
        return float("inf")
    
    return get_server_uptime_history(server) / number_of_failures

def get_server_failure_rate(server):
    """Calcula taxa de falha do servidor."""
    mtbf = get_server_mtbf(server)
    return 1 / mtbf if mtbf != 0 and mtbf != float("inf") else 0

def get_server_conditional_reliability(server, upcoming_instants):
    """Calcula confiabilidade condicional para instantes futuros."""
    server_failure_rate = get_server_failure_rate(server)
    
    if server_failure_rate == 0:
        return 100.0  # Máxima confiabilidade
    
    return (math.exp(-server_failure_rate * upcoming_instants)) * 100

def get_time_since_last_repair(server):
    """Calcula tempo desde último reparo."""
    if not server.failure_model.failure_history:
        return float("inf")
    
    current_step = server.model.schedule.steps
    if is_ongoing_failure(server, current_step):
        return 0
    
    # Encontrar reparo mais recente
    sorted_history = sorted(
        server.failure_model.failure_history, 
        key=lambda x: x["becomes_available_at"], 
        reverse=True
    )
    
    last_repair = None
    for failure in sorted_history:
        if failure["becomes_available_at"] <= current_step:
            last_repair = failure
            break
    
    if last_repair:
        return current_step + 1 - last_repair["becomes_available_at"]
    
    return float("inf")

def get_server_trust_cost(server):
    """Calcula custo de risco instantâneo do servidor."""
    failure_rate = get_server_failure_rate(server)
    time_since_repair = get_time_since_last_repair(server)
    mtbf = get_server_mtbf(server)
    
    # Casos especiais
    if failure_rate == 0 or mtbf == float("inf"):
        return 0
    
    if time_since_repair == 0:
        return float("inf")  # Servidor em falha
    
    # Cálculo do risco baseado na proporção tempo/MTBF
    proportion = time_since_repair / mtbf
    return failure_rate * proportion

def get_application_delay_score(app: object) -> float:
    """Calcula score de delay da aplicação."""
    delay_sla = app.users[0].delay_slas[str(app.id)]
    user_switch = app.users[0].base_station.network_switch
    
    edge_servers_that_dont_violate_delay_sla = 0
    available_servers = [s for s in EdgeServer.all() if s.status == "available"]
    
    for edge_server in available_servers:
        if calculate_path_delay(origin_network_switch=user_switch, target_network_switch=edge_server.network_switch) <= delay_sla:
            edge_servers_that_dont_violate_delay_sla += 1
    
    if edge_servers_that_dont_violate_delay_sla == 0:
        return 0
    else:
        return 1 / ((edge_servers_that_dont_violate_delay_sla * delay_sla) ** (1 / 2))

def get_application_access_intensity_score(app: object) -> float:
    """Calcula score de intensidade de acesso."""
    user = app.users[0]
    access_pattern = user.access_patterns[str(app.id)]
    
    duration = access_pattern.duration_values[0]
    interval = access_pattern.interval_values[0]
    
    base_score = duration / interval
    intensity_score = math.log(1 + base_score) * 10
    
    return intensity_score

def get_host_candidates(user: object, service: object) -> list:
    """Obtém lista de candidatos para hospedar serviço."""
    app_delay = user.delays[str(service.application.id)] if user.delays[str(service.application.id)] is not None else 0
    host_candidates = []
    
    available_servers = [s for s in EdgeServer.all() 
                        if s.status == "available" and get_normalized_free_capacity(s) > 0]
    
    for edge_server in available_servers:
        # Calcular delay e violações SLA
        additional_delay = calculate_path_delay(
            origin_network_switch=user.base_station.network_switch, 
            target_network_switch=edge_server.network_switch
        )
        overall_delay = app_delay + additional_delay
        sla_violations = 1 if overall_delay > user.delay_slas[str(service.application.id)] else 0
        
        # Calcular métricas do servidor
        trust_cost = get_server_trust_cost(edge_server)
        user_access_patterns = user.access_patterns[str(service.application.id)]
        service_expected_duration = user_access_patterns.duration_values[0]
        conditional_reliability = get_server_conditional_reliability(edge_server, service_expected_duration)
        power_consumption = edge_server.power_model_parameters["max_power_consumption"]
        
        # Calcular camadas não-cached
        service_image = ContainerImage.find_by(attribute_name="digest", attribute_value=service.image_digest)
        service_layers = [ContainerLayer.find_by(attribute_name="digest", attribute_value=digest) 
                         for digest in service_image.layers_digests]
        
        amount_of_uncached_layers = 0
        for service_layer in service_layers:
            is_cached = any(cached_layer.digest == service_layer.digest 
                           for cached_layer in edge_server.container_layers)
            if not is_cached:
                amount_of_uncached_layers += service_layer.size
        
        host_candidates.append({
            "object": edge_server,
            "sla_violations": sla_violations,
            "trust_cost": trust_cost,
            "conditional_reliability": conditional_reliability,
            "power_consumption": power_consumption,
            "overall_delay": overall_delay,
            "amount_of_uncached_layers": amount_of_uncached_layers,
            "free_capacity": get_normalized_free_capacity(edge_server),
        })
    
    return host_candidates

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_ongoing_failure(server, current_step=None):
    """Verifica se servidor tem falha em andamento."""
    if current_step is None:
        current_step = server.model.schedule.steps
    
    if not server.failure_model.failure_history:
        return False
    
    flatten_failure_trace = [item for failure_group in server.failure_model.failure_trace for item in failure_group]
    
    ongoing_failure = next(
        (failure for failure in flatten_failure_trace
         if failure["failure_starts_at"] <= current_step < failure["becomes_available_at"]),
        None,
    )
    
    return ongoing_failure is not None

def is_making_request(user, current_step):
    """Verifica se usuário está fazendo nova requisição."""
    for app in user.applications:
        last_access = user.access_patterns[str(app.id)].history[-1]
        if current_step == last_access["start"]:
            return True
    return False

def get_application_downtime(application):
    """Calcula downtime da aplicação durante simulação."""
    return sum(1 for status in application.availability_history if status is False)

def get_application_uptime(application):
    """Calcula uptime da aplicação durante simulação."""
    return sum(1 for status in application.availability_history if status is True)

def get_user_perceived_downtime(application):
    """Calcula downtime percebido pelo usuário."""
    return sum(1 for status in application.downtime_history if status)

# ============================================================================
# DISPLAY AND MONITORING FUNCTIONS
# ============================================================================

def display_simulation_metrics(simulation_parameters):
    """Exibe métricas detalhadas da simulação."""
    current_step = simulation_parameters.get("current_step")
    
    # Métricas de servidores
    server_metrics = {}
    for server in EdgeServer.all():
        server_metrics[f"Server {server.id}"] = {
            "Risk Cost": get_server_trust_cost(server),
            "Simulation Uptime": get_server_uptime_simulation(server),
            "Simulation Downtime": get_server_downtime_simulation(server),
            "History Uptime": get_server_uptime_history(server),
            "History Downtime": get_server_downtime_history(server),
            "MTBF": get_server_mtbf(server),
            "MTTR": get_server_mttr(server),
            "Failure Rate": get_server_failure_rate(server),
            "Reliability_10": get_server_conditional_reliability(server, 10),
            "Reliability_60": get_server_conditional_reliability(server, 60),
            "Time Since Last Repair": get_time_since_last_repair(server),
            "Total Failures": get_server_total_failures(server)
        }
    
    # Métricas de aplicações
    application_metrics = {}
    for application in Application.all():
        application_metrics[f"Application {application.id}"] = {
            "Uptime": get_application_uptime(application),
            "Downtime": get_application_downtime(application)
        }
    
    # Métricas de usuários
    user_metrics = {}
    total_perceived_downtime = 0
    for user in User.all():
        user_entry = {}
        for application in user.applications:
            perceived_downtime = get_user_perceived_downtime(application)
            user_entry[f"Application {application.id} Perceived Downtime"] = perceived_downtime
            total_perceived_downtime += perceived_downtime
        user_metrics[f"User {user.id}"] = user_entry
    
    # Métricas da fila de espera
    waiting_queue_metrics = {
        "Total Applications in Queue": len(_waiting_queue),
        "Applications by Priority": {}
    }
    
    if _waiting_queue:
        priorities = {}
        for item in _waiting_queue:
            priority = int(item["priority_score"] // 100)  # Agrupa por centenas
            priorities[priority] = priorities.get(priority, 0) + 1
        waiting_queue_metrics["Applications by Priority"] = priorities
    
    metrics = {
        "Simulation Parameters": simulation_parameters,
        "Infrastructure": f"{Application.count()}/{Service.count()}/{User.count()}/{EdgeServer.count()}",
        "Waiting Queue": waiting_queue_metrics,
        "Server Metrics": server_metrics,
        "Application Metrics": application_metrics,
        "User Perceived Downtime": user_metrics,
    }
    
    print(dumps(metrics, indent=4))
    print(f"Total Perceived Downtime: {total_perceived_downtime}")

def display_reliability_metrics(parameters: dict = {}):
    """Exibe resumo das métricas de confiabilidade."""
    current_step = parameters.get("current_step")
    
    print(f"\n\nStep: {current_step}")
    print("=" * 125)
    print("MÉTRICAS DOS SERVIDORES DISPONÍVEIS".center(125))
    print("=" * 125)
    
    available_servers = [s for s in EdgeServer.all() if s.status == "available"]
    servers = sorted(available_servers, key=lambda s: get_server_trust_cost(s))
    
    # Cabeçalho
    header = f"{'Rank':^5}|{'ID':^5}|{'Status':^10}|{'Custo Risco':^12}|{'Taxa Falha':^12}|{'T.Últ.Rep':^10}|{'MTBF':^10}|{'MTTR':^8}|{'Falhas':^8}|{'Conf.10':^8}|{'Conf.60':^8}|"
    print(header)
    print("-" * 125)
    
    for rank, server in enumerate(servers, 1):
        mtbf = get_server_mtbf(server)
        time_since_repair = get_time_since_last_repair(server)
        risk_cost = get_server_trust_cost(server)
        
        # Formatação especial para valores infinitos
        mtbf_str = "∞" if mtbf == float("inf") else f"{mtbf:.2f}"
        time_repair_str = "Never" if time_since_repair == float("inf") else f"{time_since_repair:.2f}"
        risk_cost_str = "Mínimo" if risk_cost == 0 else f"{risk_cost:.4f}"
        
        row = f"{rank:^5}|{server.id:^5}|{server.status:^10}|{risk_cost_str:^12}|{get_server_failure_rate(server):^12.6f}|{time_repair_str:^10}|{mtbf_str:^10}|{get_server_mttr(server):^8.2f}|{get_server_total_failures(server):^8}|{get_server_conditional_reliability(server, 10):^8.2f}|{get_server_conditional_reliability(server, 60):^8.2f}|"
        print(row)

def display_application_info():
    """Exibe informações sobre aplicações e servidores."""
    print("\n" + "=" * 50)
    print("INFORMAÇÕES DE APLICAÇÕES E SERVIDORES".center(50))
    print("=" * 50)
    
    header = f"{'App ID':^12}|{'Server ID':^12}|{'User ID':^12}|{'Status':^10}"
    print(header)
    print("-" * 50)
    
    for application in Application.all():
        service = application.services[0] if application.services else None
        server_id = service.server.id if service and service.server else "N/A"
        
        users = application.users
        if users:
            for user in users:
                status = "Online" if application.availability_status else "Offline"
                row = f"{application.id:^12}|{server_id:^12}|{user.id:^12}|{status:^10}"
                print(row)
        else:
            status = "Online" if application.availability_status else "Offline"
            row = f"{application.id:^12}|{server_id:^12}|{'N/A':^12}|{status:^10}"
            print(row)