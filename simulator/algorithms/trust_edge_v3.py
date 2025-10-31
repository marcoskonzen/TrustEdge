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
    """Retorna os contadores de migração."""
    return _migration_counters

def reset_migration_counters():
    """Reseta os contadores de migração."""
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
    """Incrementa contadores de migração."""
    global _migration_counters
    
    # Contador total
    _migration_counters["total"] += 1
    
    # Contador por motivo
    if reason in _migration_counters["by_reason"]:
        _migration_counters["by_reason"][reason] += 1
    
    # Contador por step
    if current_step not in _migration_counters["by_step"]:
        _migration_counters["by_step"][current_step] = 0
    _migration_counters["by_step"][current_step] += 1
    
    # Contador de sucesso/falha
    if success:
        _migration_counters["successful"] += 1
        status_str = "✓ SUCESSO"
    else:
        _migration_counters["failed"] += 1
        status_str = "✗ FALHA"
    
    # Log detalhado
    print(f"[MIGRATION_COUNTER] Migração #{_migration_counters['total']}")
    print(f"                    Motivo: {reason}")
    print(f"                    Step: {current_step}")
    print(f"                    Status: {status_str}")
    print(f"                    Totais - Success: {_migration_counters['successful']}, Failed: {_migration_counters['failed']}")

def print_migration_summary():
    """Imprime resumo das migrações realizadas."""
    counters = get_migration_counters()
    
    print(f"\n{'='*60}")
    print(f"RESUMO DE MIGRAÇÕES")
    print(f"{'='*60}")
    print(f"Total de migrações: {counters['total']}")
    print(f"Migrações bem-sucedidas: {counters['successful']}")
    print(f"Migrações mal-sucedidas: {counters['failed']}")
    
    if counters['total'] > 0:
        success_rate = (counters['successful'] / counters['total']) * 100
        print(f"Taxa de sucesso: {success_rate:.2f}%")
    
    print(f"\nMigrações por motivo:")
    for reason, count in counters['by_reason'].items():
        if count > 0:
            percentage = (count / counters['total']) * 100 if counters['total'] > 0 else 0
            print(f"  - {reason}: {count} ({percentage:.1f}%)")
    
    print(f"{'='*60}\n")

def get_migration_statistics():
    """Retorna estatísticas detalhadas das migrações para análise."""
    counters = get_migration_counters()
    
    stats = {
        "total_migrations": counters["total"],
        "successful_migrations": counters["successful"],
        "failed_migrations": counters["failed"],
        "success_rate": (counters["successful"] / counters["total"]) * 100 if counters["total"] > 0 else 0,
        "migrations_by_reason": counters["by_reason"].copy(),
        "migrations_by_step": counters["by_step"].copy(),
        "most_active_step": max(counters["by_step"].items(), key=lambda x: x[1]) if counters["by_step"] else None,
        "average_migrations_per_step": sum(counters["by_step"].values()) / len(counters["by_step"]) if counters["by_step"] else 0
    }
    
    return stats

def initialize_migration_tracking():
    """Inicializa o sistema de rastreamento de migrações."""
    reset_migration_counters()
    print("[LOG] Sistema de rastreamento de migrações inicializado")


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
        "delay_sla": user.delay_slas[str(application.id)],
        "delay_score": get_application_delay_score(application),
        "intensity_score": get_application_access_intensity_score(application),
        "demand_resource": get_normalized_demand(application.services[0]),
        "delay_urgency": get_delay_urgency(application, user)
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

    # Inicializar contadores na primeira execução
    if current_step == 0:
        initialize_migration_tracking()
    
    # 1. ATUALIZAR DELAYS
    update_application_delays(current_step)

    # 2. PROCESSAR FILA DE ESPERA
    process_waiting_queue(current_step)

    # 3. MONITORAMENTO E MIGRAÇÃO
    monitor_and_migrate_services(parameters)

    # 4. PROVISIONAMENTO DE NOVAS REQUISIÇÕES
    provision_new_requests(current_step)

     # 5. ATUALIZAR DOWNTIME PERCEBIDO (UMA VEZ POR STEP)
    update_user_perceived_downtime_for_current_step()

    # 6. COLETA DE MÉTRICAS
    collect_sla_violations_for_current_step()
    collect_infrastructure_metrics_for_current_step()
    #display_simulation_metrics(simulation_parameters=parameters)

    # 7. RELATÓRIO FINAL DE MIGRAÇÕES
    if parameters.get("time_steps") == current_step + 1:
        print_migration_summary()

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

    waiting_queue_metadata = []
    for waiting_item in _waiting_queue:
        waiting_queue_metadata.append({
            "priority_score": waiting_item["priority_score"],
            "delay_score": waiting_item["delay_score"],
            "intensity_score": waiting_item["intensity_score"],
            "demand_resource": waiting_item["demand_resource"],
            "delay_urgency": waiting_item["delay_urgency"],
        })

    min_and_max_app = find_minimum_and_maximum(metadata=waiting_queue_metadata)

    # Ordenar fila de espera
    # _waiting_queue.sort(key=lambda app: (
    #     app["delay_urgency"],                     # Mais próximo da violação primeiro
    # )
    # )

    _waiting_queue.sort(key=lambda item: (
        #-item["priority_score"],  # Maior prioridade primeiro
        item["delay_urgency"]   # Mais próximo da violação primeiro
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

def get_delay_urgency(application, user):
    """Calcula urgência baseada na proximidade da violação de SLA."""
    user_app = user
    app = application
    current_delay = user_app.delays[str(app.id)] if user_app.delays[str(app.id)] is not None else 0
    delay_sla = user_app.delay_slas[str(app.id)]
    return delay_sla - current_delay  # Quanto menor, mais urgente

# ============================================================================
# SERVICE MONITORING AND MIGRATION
# ============================================================================

def monitor_and_migrate_services(parameters: dict = {}):
    """Monitora servidores e migra serviços quando necessário."""
    current_step = parameters.get("current_step") - 1
    reliability_threshold = 70.0
    delay_threshold = 1 # 120% do SLA
    
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
    processed_services = set()
    
    for user in User.all():
        active_applications = get_active_applications_with_remaining_time(user, current_step)
        
        for app_info in active_applications:
            app = app_info["application"]
            service = app.services[0]
            server = service.server

            if service.id in processed_services:
                continue
            processed_services.add(service.id)

            # Pular aplicações recém-provisionadas
            if is_making_request(user, current_step):
                print(f"[DEBUG] App {app.id} recém-provisionada - pulando migração")
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
    if (not service.server and is_user_accessing_application(user, app, current_step)):
        return {
            "needs_migration": True,
            "reason": "server_failed",
            "priority": 1
        }
    
    # 2. Violação de delay
    current_delay = user.delays[str(app.id)] if user.delays[str(app.id)] is not None else 0
    delay_sla = user.delay_slas[str(app.id)]
    delay_limit = delay_sla * delay_threshold
    
    print(f"[LOG] Avaliando delay para aplicação {app.id}: Current={current_delay}, SLA={delay_sla}, Limit={delay_limit}")
    
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
            "priority": 2,
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
        if (not current_server):
            print(f"[LOG] Servidor atual: NENHUM (Servidor falhou)")
        else:
            print(f"[LOG] Servidor atual: {current_server.id} (Status: {current_server.status})")

        # Encontrar servidor de destino
        target_server = find_migration_target(user, service, current_server, reason)
        
        if target_server:
            if initiate_service_migration(service, target_server, reason, current_step):
                increment_migration_counter(reason, current_step, success=True)
            else:
                # Falha na execução da migração
                increment_migration_counter(reason, current_step, success=False)
        else:
            # FALHA: Sem servidor disponível - migração não foi possível
            increment_migration_counter(reason, current_step, success=False)

            if not current_server:
                # Servidor falhou E não há alternativa - DESPROVISIONAMENTO
                print(f"[LOG] Servidor atual falhou e sem alternativas - movendo ou mantendo na fila de espera")
               
               # Adicionar à fila de espera com alta prioridade (falha de servidor)
                priority_score = 999.0  # Prioridade máxima para falhas de servidor
                add_to_waiting_queue(user, app, service, priority_score)
            
            elif current_server.status == "available":
                print(f"[LOG] Sem servidor disponível - mantendo no servidor atual {current_server.id}")

def find_migration_target(user, service, current_server, migration_reason):
    """Encontra o melhor servidor de destino para migração."""
    available_servers = get_host_candidates(user,service)
    
    if not available_servers:
        return None
    
    # Avaliar candidatos com foco em cache e proximidade
    migration_candidates = [
        candidate for candidate in available_servers
        if not current_server or candidate["object"].id != current_server.id
    ]
    
    if not migration_candidates:
        print(f"[LOG] ⚠️  Nenhuma alternativa melhor que servidor atual {current_server.id}")
        return None
    
    # Priorizar servidores que não violam SLA
    migration_candidates = sort_host_candidates(migration_candidates)
    
    # Filtrar apenas candidatos que melhoram a situação
    best_candidates = []
    current_delay = user.delays[str(service.application.id)]
    current_sla = user.delay_slas[str(service.application.id)]
    
    for candidate in migration_candidates:
        candidate_delay = candidate["overall_delay"]
        
        # Para violação de delay: só migrar se melhora significativamente
        if migration_reason == "delay_violation":
            if candidate_delay < current_delay * 0.9:  # 10% de melhoria mínima
                best_candidates.append(candidate)
        else:
            # Para outros motivos: qualquer servidor sem violação SLA
            if candidate["sla_violations"] == 0:
                best_candidates.append(candidate)
    
    if not best_candidates:
        print(f"[LOG] ⚠️  Nenhum candidato melhora a situação atual")
        return None
    
    # Retornar melhor candidato disponível
    for candidate in best_candidates:
        edge_server = candidate["object"]
        if edge_server.has_capacity_to_host(service):
            return edge_server
    
    return None


def initiate_service_migration(service, target_server, reason, current_step):
    """Inicia migração de serviço usando infraestrutura EdgeSimPy."""
    if service.server:
        print(f"[LOG] ✓ Iniciando migração {service.server.id} → {target_server.id}")
    else:
        print(f"[LOG] ✓ Iniciando migração NENHUM → {target_server.id} (Servidor falhou)")
    
    app = service.application
    user = app.users[0]
    edge_server = target_server

    try:
        # Incrementar contadores de migração
        if service.server:
            service.server.ongoing_migrations += 1
        target_server.ongoing_migrations += 1
        
        provision(user=user, application=app, service=service, edge_server=edge_server)
        #service.provision(target_server=edge_server)

        user.set_communication_path(app=app)
        new_delay = user._compute_delay(app=app, metric="latency")
        user.delays[str(app.id)] = new_delay
    
        # DEBUG: Verificar se o delay foi atualizado
        print(f"[DEBUG] Delay pós-provisionamento App {app.id}: {new_delay}")
        
        # Adicionar metadados sobre a migração
        if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
            migration = service._Service__migrations[-1]
            migration["migration_reason"] = reason
            migration["triggered_at_step"] = current_step
            
            print(f"[LOG] Migração iniciada - Status: {migration['status']}")

        return True
        
    except Exception as e:
        print(f"[LOG] ✗ Erro ao iniciar migração: {e}")
        # Reverter contadores em caso de erro
        if service.server:
            service.server.ongoing_migrations -= 1
        target_server.ongoing_migrations -= 1
        return False

def update_application_delays(current_step):
    """Atualiza apenas delays - SEM lógica de downtime percebido."""
    print(f"[DEBUG] === ATUALIZANDO DELAYS - STEP {current_step} ===")
    
    for user in User.all():
        for app in user.applications:
            service = app.services[0]
            
            if is_making_request(user, current_step):
                print(f"[DEBUG] App {app.id} recém solicitando provisionamento - pulando atualização de delay")
                continue
            
            if is_user_accessing_application(user, app, current_step):
                old_delay = user.delays[str(app.id)]
                
                if service.server and service.server.status == "available":
                    user.set_communication_path(app=app)
                    new_delay = user._compute_delay(app=app, metric="latency")
                    user.delays[str(app.id)] = new_delay
                    print(f"[DEBUG] App {app.id}: Delay {old_delay} → {new_delay}")
                else:
                    # Aplicação indisponível - delay infinito
                    user.delays[str(app.id)] = float('inf')
                    print(f"[DEBUG] App {app.id}: INDISPONÍVEL - delay infinito")
            else:
                # Usuário não está acessando
                if user.delays[str(app.id)] != 0:
                    user.delays[str(app.id)] = 0

    

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
                    "delay_urgency": get_delay_urgency(app, user)
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
    ), reverse=True
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
        #min_and_max_app = find_minimum_and_maximum(metadata=all_apps_metadata)
        priority_score = app_metadata["delay_urgency"]
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
            print(f"      Delay previsto: {edge_server_metadata['overall_delay']}")
            print(f"      SLA: {user.delay_slas[str(app.id)]}")
            print(f"      Viola SLA: {'SIM' if edge_server_metadata['sla_violations'] else 'NÃO'}")
            
            provision(user=user, application=app, service=service, edge_server=edge_server)
            #service.provision(target_server=edge_server)

            return True
    
    print(f"[LOG] ✗ Servidores sem capacidade para aplicação {app.id}")
    return False

def sort_host_candidates(edge_servers):
    """Ordena candidatos por adequação para hospedagem."""
    if not edge_servers:
        return edge_servers
    
    # Filtrar valores numéricos para normalização
    numeric_metadata = []
    for server_data in edge_servers:
        numeric_metadata.append({
            "trust_cost": server_data["trust_cost"],
            "overall_delay": server_data["overall_delay"],
            "amount_of_uncached_layers": server_data["amount_of_uncached_layers"],
            "power_consumption": server_data["power_consumption"],
        })
    
    min_and_max = find_minimum_and_maximum(metadata=numeric_metadata)
    
    return sorted(
        edge_servers,
        key=lambda s: (
            s["sla_violations"],
            get_norm(metadata=s, attr_name="trust_cost", min=min_and_max["minimum"], max=min_and_max["maximum"]) +
            get_norm(metadata=s, attr_name="amount_of_uncached_layers", min=min_and_max["minimum"], max=min_and_max["maximum"]) +
            get_norm(metadata=s, attr_name="overall_delay", min=min_and_max["minimum"], max=min_and_max["maximum"]),
        ),
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
    
    return last_access["end"] - current_step

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