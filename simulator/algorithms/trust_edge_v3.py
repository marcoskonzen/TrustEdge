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
# GLOBAL PROVISIONING AND MIGRATION TRACKING SYSTEM
# ============================================================================

_provisioning_and_migration_metrics = {
    # Provisionamentos (origin = None)
    "total_provisionings": 0,
    "provisionings_finished": 0,
    "provisionings_interrupted": 0,
    
    # Migrações (origin != None)
    "total_migrations": 0,
    "migrations_finished": 0,
    "migrations_interrupted": 0,
    
    # Migrações por motivo
    "migrations_by_reason": {
        "server_failed": 0,
        "delay_violation": 0,
        "low_reliability": 0
    },
    
    # Detalhes para auditoria
    "by_step": {},
}

def initialize_provisioning_and_migration_tracking():
    """Inicializa o sistema unificado de rastreamento."""
    global _provisioning_and_migration_metrics
    _provisioning_and_migration_metrics = {
        "total_provisionings": 0,
        "provisionings_finished": 0,
        "provisionings_interrupted": 0,
        "total_migrations": 0,
        "migrations_finished": 0,
        "migrations_interrupted": 0,
        "migrations_by_reason": {
            "server_failed": 0,
            "delay_violation": 0,
            "low_reliability": 0
        },
        "by_step": {},
    }
    print("[LOG] Sistema unificado de rastreamento inicializado")

def collect_final_provisioning_and_migration_metrics():
    """
    Coleta métricas finais AUDITANDO todas as migrações registradas.
    Executa ao final da simulação.
    """
    global _provisioning_and_migration_metrics
    
    print(f"\n{'='*70}")
    print(f"COLETANDO MÉTRICAS FINAIS DE PROVISIONAMENTO E MIGRAÇÃO")
    print(f"{'='*70}\n")
    
    # Resetar contadores (vamos recontabilizar do zero)
    _provisioning_and_migration_metrics["total_provisionings"] = 0
    _provisioning_and_migration_metrics["provisionings_finished"] = 0
    _provisioning_and_migration_metrics["provisionings_interrupted"] = 0
    _provisioning_and_migration_metrics["total_migrations"] = 0
    _provisioning_and_migration_metrics["migrations_finished"] = 0
    _provisioning_and_migration_metrics["migrations_interrupted"] = 0
    _provisioning_and_migration_metrics["migrations_by_reason"] = {
        "server_failed": 0,
        "delay_violation": 0,
        "low_reliability": 0
    }
    
    # Auditar TODAS as operações registradas nos serviços
    for service in Service.all():
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            continue
        
        for migration in service._Service__migrations:
            origin = migration.get("origin")
            status = migration.get("status", "unknown")
            reason = migration.get("migration_reason", "unknown")
            
            # ═══════════════════════════════════════════════════════════
            # CLASSIFICAR: Provisionamento vs Migração
            # ═══════════════════════════════════════════════════════════
            is_provisioning = (origin is None)
            
            if is_provisioning:
                # PROVISIONAMENTO
                _provisioning_and_migration_metrics["total_provisionings"] += 1
                
                if status == "finished":
                    _provisioning_and_migration_metrics["provisionings_finished"] += 1
                elif status == "interrupted":
                    _provisioning_and_migration_metrics["provisionings_interrupted"] += 1
                
            else:
                # MIGRAÇÃO
                _provisioning_and_migration_metrics["total_migrations"] += 1
                
                if status == "finished":
                    _provisioning_and_migration_metrics["migrations_finished"] += 1
                elif status == "interrupted":
                    _provisioning_and_migration_metrics["migrations_interrupted"] += 1
                
                # Contabilizar por motivo
                if reason in _provisioning_and_migration_metrics["migrations_by_reason"]:
                    _provisioning_and_migration_metrics["migrations_by_reason"][reason] += 1
    
    print(f"✓ Métricas coletadas com sucesso\n")

def print_final_provisioning_and_migration_summary():
    """
    Imprime resumo consolidado e consistente ao final da simulação.
    """
    metrics = _provisioning_and_migration_metrics
    
    print(f"\n{'='*70}")
    print(f"RESUMO CONSOLIDADO DE PROVISIONAMENTO E MIGRAÇÃO")
    print(f"{'='*70}\n")
    
    # ═══════════════════════════════════════════════════════════
    # PROVISIONAMENTOS
    # ═══════════════════════════════════════════════════════════
    print(f"PROVISIONAMENTOS (Inicial - origin=None):")
    print(f"  Total de provisionamentos iniciados: {metrics['total_provisionings']}")
    
    if metrics['total_provisionings'] > 0:
        finished_pct = (metrics['provisionings_finished'] / metrics['total_provisionings']) * 100
        interrupted_pct = (metrics['provisionings_interrupted'] / metrics['total_provisionings']) * 100
        
        print(f"  └─ Finalizados com sucesso: {metrics['provisionings_finished']} ({finished_pct:.1f}%)")
        print(f"  └─ Interrompidos: {metrics['provisionings_interrupted']} ({interrupted_pct:.1f}%)")
    else:
        print(f"  └─ Nenhum provisionamento registrado")
    
    print()
    
    # ═══════════════════════════════════════════════════════════
    # MIGRAÇÕES
    # ═══════════════════════════════════════════════════════════
    print(f"MIGRAÇÕES (origin != None):")
    print(f"  Total de migrações iniciadas: {metrics['total_migrations']}")
    
    if metrics['total_migrations'] > 0:
        finished_pct = (metrics['migrations_finished'] / metrics['total_migrations']) * 100
        interrupted_pct = (metrics['migrations_interrupted'] / metrics['total_migrations']) * 100
        
        print(f"  └─ Finalizadas com sucesso: {metrics['migrations_finished']} ({finished_pct:.1f}%)")
        print(f"  └─ Interrompidas: {metrics['migrations_interrupted']} ({interrupted_pct:.1f}%)")
        
        print(f"\n  Migrações por motivo:")
        for reason, count in metrics['migrations_by_reason'].items():
            if count > 0:
                reason_pct = (count / metrics['total_migrations']) * 100
                print(f"    └─ {reason}: {count} ({reason_pct:.1f}%)")
    else:
        print(f"  └─ Nenhuma migração registrada")
    
    print(f"\n{'='*70}\n")

def get_provisioning_and_migration_metrics():
    """Retorna as métricas para análise externa."""
    return _provisioning_and_migration_metrics.copy()


def audit_migration_times():
    """Audita tempos de migração para detectar anomalias (DEBUG)."""
    anomalies = []
    
    print(f"\n{'='*70}")
    print(f"AUDITORIA DE TEMPOS DE MIGRAÇÃO (DEBUG)")
    print(f"{'='*70}\n")
    
    for service in Service.all():
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            continue
        
        for i, mig in enumerate(service._Service__migrations):
            if mig["end"] is None:
                continue  # Pular migrações ativas
            
            duration = mig['end'] - mig['start']
            
            # Calcular tempo rastreado
            tracked_time = (
                mig.get('waiting_time', 0) + 
                mig.get('pulling_layers_time', 0) + 
                mig.get('migrating_service_state_time', 0) +
                mig.get('interrupted_time', 0)
            )
            
            discrepancy = duration - tracked_time
            
            # Verificar anomalia (tolerância de 1 step)
            if discrepancy > 1:
                origin = mig.get("origin")
                target = mig.get("target")
                status = mig.get("status", "unknown")
                
                print(f"⚠️ ANOMALIA - Serviço {service.id} | Migração {i+1}")
                print(f"   Status: {status}")
                print(f"   Origin: {origin.id if origin else 'None'} → Target: {target.id if target else 'None'}")
                print(f"   Duração: {duration} steps | Rastreado: {tracked_time} steps")
                print(f"   Missing: {discrepancy} steps\n")
                
                anomalies.append({
                    'service': service.id,
                    'migration': i + 1,
                    'duration': duration,
                    'tracked': tracked_time,
                    'missing': discrepancy,
                    'status': status
                })
    
    if anomalies:
        print(f"Total de anomalias encontradas: {len(anomalies)}")
    else:
        print(f"✓ Nenhuma anomalia detectada")
    
    print(f"{'='*70}\n")


def audit_server_resources(current_step):
    """Audita consistência dos recursos dos servidores."""
    
    if current_step % 50 != 0:
        return
    
    print(f"\n[AUDITORIA] === VERIFICAÇÃO DE RECURSOS - STEP {current_step} ===")
    
    anomalies_found = False
    
    # ✅ NOVO: Detectar serviços duplicados
    service_locations = {}  # {service_id: [server_ids]}
    
    for server in EdgeServer.all():
        # Verificar recursos negativos
        cpu_available = server.cpu - server.cpu_demand
        memory_available = server.memory - server.memory_demand
        
        if cpu_available < 0 or memory_available < 0:
            anomalies_found = True
            print(f"[AUDITORIA] ⚠️ SERVIDOR {server.id} COM RECURSOS NEGATIVOS!")
            print(f"            CPU disponível: {cpu_available}/{server.cpu}")
            print(f"            Memory disponível: {memory_available}/{server.memory}")
        
        # Verificar inconsistências de relacionamento
        for service in server.services:
            # Rastrear localização do serviço
            if service.id not in service_locations:
                service_locations[service.id] = []
            service_locations[service.id].append(server.id)
            
            if service.server != server:
                anomalies_found = True
                print(f"[AUDITORIA] ⚠️ INCONSISTÊNCIA: Serviço {service.id} na lista do servidor {server.id}")
                print(f"            mas service.server = {service.server.id if service.server else None}")
    
    # ✅ Verificar duplicatas
    for service_id, server_ids in service_locations.items():
        if len(server_ids) > 1:
            anomalies_found = True
            print(f"[AUDITORIA] ⚠️ DUPLICATA: Serviço {service_id} está em MÚLTIPLOS servidores!")
            print(f"            Servidores: {server_ids}")
    
    if not anomalies_found:
        print(f"[AUDITORIA] ✅ Nenhuma anomalia detectada")
    
    print(f"[AUDITORIA] === FIM VERIFICAÇÃO ===\n")

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

    user.delays[str(application.id)] = float('inf')  # Definir delay como infinito enquanto estiver na fila

    waiting_item = {
        "user": user,
        "application": application,
        "service": service,
        "priority_score": priority_score,
        "queued_at_step": user.model.schedule.steps,
        "delay": user.delays[str(application.id)],
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


def diagnose_layer_downloads(current_step):
    """Diagnostica de onde as camadas estão sendo baixadas e limitações."""
    
    print("=" * 70)
    print(f"[DEBUG_DOWNLOADS] === ANÁLISE DE DOWNLOADS DE CAMADAS - STEP {current_step} ===")
    print("=" * 70)

    registries = ContainerRegistry.all()
    
    if not registries:
        print(f"[DEBUG_DOWNLOADS] ⚠️ Nenhum Container Registry encontrado!")
        return
    
    print(f"[DEBUG_DOWNLOADS] ✓ Container Registries encontrados: {len(registries)}")
    
    for registry in registries:
        if not hasattr(registry, 'server') or registry.server is None:
            continue
        
        total_layers = sum(1 for layer in ContainerLayer.all() 
                          if hasattr(layer, 'server') and layer.server and layer.server.id == registry.server.id)
        
        print(f"[DEBUG_DOWNLOADS]   Registry {registry.id}:")
        print(f"                 - Camadas armazenadas: {total_layers}")
    
    # Verificar servidores com downloads ativos
    servers_with_activity = []
    total_active_downloads = 0
    
    # ✅ NOVO: Rastrear camadas em download ativo
    layers_being_downloaded = set()
    
    for server in EdgeServer.all():
        # Coletar camadas em download ativo
        for flow in server.download_queue:
            if hasattr(flow, 'metadata') and flow.metadata.get('type') == 'layer':
                layer = flow.metadata.get('object')
                if layer and hasattr(layer, 'digest'):
                    layers_being_downloaded.add(layer.digest)
        
        if len(server.download_queue) > 0 or len(server.services) > 0:
            has_inconsistency = False
            
            if len(server.download_queue) > 0 and server.cpu_demand == 0 and server.memory_demand == 0:
                has_inconsistency = True
            
            if len(server.services) > 0 and server.cpu_demand == 0 and server.memory_demand == 0:
                has_inconsistency = True
            
            if len(server.download_queue) > 0:
                servers_with_activity.append(server)
                total_active_downloads += len(server.download_queue)
            
            if len(server.download_queue) > 0 or len(server.services) > 0:
                status_icon = "⚠️" if has_inconsistency else " "
                print(f"[DEBUG_DOWNLOADS] {status_icon} Servidor {server.id}:")
                print(f"               - Serviços alocados: {len(server.services)} (IDs: {[s.id for s in server.services]})")
                print(f"               - Downloads ativos: {len(server.download_queue)}")
                print(f"               - Waiting queue: {len(server.waiting_queue)}")
                print(f"               - Recursos: CPU={server.cpu_demand}/{server.cpu}, MEM={server.memory_demand}/{server.memory}")
                
                if has_inconsistency:
                    print(f"               ❌ SERVIDOR FALHOU!")
    
    print(f"[DEBUG_DOWNLOADS] Total de downloads ativos: {total_active_downloads}")
    print(f"[DEBUG_DOWNLOADS] Servidores com downloads: {len(servers_with_activity)}")
    print(f"[DEBUG_DOWNLOADS] === FIM DO DEBUG DE DOWNLOADS ===\n")
    
    # ✅ ESTATÍSTICAS DETALHADAS
    all_layers = ContainerLayer.all()
    
    # Categorizar camadas
    layers_in_registry = set()  # Camadas do registry (templates)
    layers_in_servers = set()   # Camadas já baixadas nos servidores
    layers_orphaned = []         # Camadas órfãs reais (lixo)
    
    # 1. Identificar camadas do registry
    for registry in registries:
        if hasattr(registry, 'server') and registry.server:
            for layer in registry.server.container_layers:
                if hasattr(layer, 'digest'):
                    layers_in_registry.add(layer.digest)
    
    # 2. Identificar camadas nos servidores
    for layer in all_layers:
        if hasattr(layer, 'server') and layer.server:
            if hasattr(layer, 'digest'):
                layers_in_servers.add(layer.digest)
    
    # 3. Identificar camadas órfãs (excluindo as que estão em download)
    for layer in all_layers:
        if not hasattr(layer, 'server') or layer.server is None:
            layer_digest = layer.digest if hasattr(layer, 'digest') else None
            
            # Excluir se está no registry (template válido)
            if layer_digest in layers_in_registry:
                continue
            
            # ✅ NOVO: Excluir se está sendo baixada ativamente
            if layer_digest in layers_being_downloaded:
                continue
            
            # É uma camada órfã real
            layers_orphaned.append(layer)
    
    print(f"[DEBUG_DOWNLOADS] Estatísticas gerais:")
    print(f"               - Total de camadas no sistema: {len(all_layers)}")
    print(f"               - Camadas em registries (templates): {len(layers_in_registry)}")
    print(f"               - Camadas em servidores: {len(layers_in_servers)}")
    print(f"               - Camadas em download ativo: {len(layers_being_downloaded)}")
    print(f"               - Camadas órfãs (lixo): {len(layers_orphaned)}")
    
    if layers_orphaned:
        print(f"\n[DEBUG_DOWNLOADS] ⚠️ Camadas órfãs detectadas:")
        for i, layer in enumerate(layers_orphaned[:5], 1):
            layer_digest = layer.digest[:8] if hasattr(layer, 'digest') else 'N/A'
            layer_size = layer.size if hasattr(layer, 'size') else 0
            print(f"               {i}. Layer {layer_digest} (ID: {layer.id}, Size: {layer_size})")
        
        if len(layers_orphaned) > 5:
            print(f"               ... e mais {len(layers_orphaned) - 5} camadas órfãs")
    
    print(f"[DEBUG_DOWNLOADS] === FIM DO DEBUG DE DOWNLOADS ===\n")


# ...existing code...
def collect_server_resource_snapshot(current_step):
    """Retorna uso e disponibilidade de recursos dos servidores no step informado."""
    
    print()
    print("=" * 70)
    print(f"[DEBUG_STATUS_SERVER] === SNAPSHOT SERVERS - STEP {current_step} ===")
    print("=" * 70)

    snapshot = []

    total_cpu = 0
    total_memory = 0
    total_cpu_demand = 0
    total_memory_demand = 0

    available_cpu_capacity = 0
    available_memory_capacity = 0
    available_cpu_demand = 0
    available_memory_demand = 0

    unavailable_cpu_capacity = 0
    unavailable_memory_capacity = 0

    def _pct(value, reference):
        return (value / reference * 100) if reference else 0.0

    for server in EdgeServer.all():
        cpu_available = server.cpu - server.cpu_demand
        mem_available = server.memory - server.memory_demand

        entry = {
            "step": current_step,
            "server_id": server.id,
            "status": server.status,
            "available": server.available,
            "cpu_total": server.cpu,
            "cpu_demand": server.cpu_demand,
            "cpu_available": cpu_available,
            "memory_total": server.memory,
            "memory_demand": server.memory_demand,
            "memory_available": mem_available,
        }
        snapshot.append(entry)

        print(
            f"[SERVER_SNAPSHOT] Server {server.id} | "
            f"Status={server.status} | Available={server.available} | "
            f"CPU {server.cpu_demand}/{server.cpu} (free={cpu_available}) | "
            f"MEM {server.memory_demand}/{server.memory} (free={mem_available})"
        )

        # Totais globais
        total_cpu += server.cpu
        total_memory += server.memory
        total_cpu_demand += server.cpu_demand
        total_memory_demand += server.memory_demand

        if server.available:
            available_cpu_capacity += server.cpu
            available_memory_capacity += server.memory
            available_cpu_demand += server.cpu_demand
            available_memory_demand += server.memory_demand
        else:
            unavailable_cpu_capacity += server.cpu
            unavailable_memory_capacity += server.memory

    unavailable_cpu_capacity = max(0, total_cpu - available_cpu_capacity)
    unavailable_memory_capacity = max(0, total_memory - available_memory_capacity)

    summary = {
        "step": current_step,
        "totals": {
            "cpu": total_cpu,
            "memory": total_memory,
        },
        "available_resources": {
            "cpu": available_cpu_capacity,
            "cpu_pct_of_total": _pct(available_cpu_capacity, total_cpu),
            "memory": available_memory_capacity,
            "memory_pct_of_total": _pct(available_memory_capacity, total_memory),
        },
        "unavailable_resources": {
            "cpu": unavailable_cpu_capacity,
            "cpu_pct_of_total": _pct(unavailable_cpu_capacity, total_cpu),
            "memory": unavailable_memory_capacity,
            "memory_pct_of_total": _pct(unavailable_memory_capacity, total_memory),
        },
        "consumption": {
            "cpu": total_cpu_demand,
            "cpu_pct_of_total": _pct(total_cpu_demand, total_cpu),
            "cpu_pct_of_available": _pct(available_cpu_demand, available_cpu_capacity),
            "memory": total_memory_demand,
            "memory_pct_of_total": _pct(total_memory_demand, total_memory),
            "memory_pct_of_available": _pct(available_memory_demand, available_memory_capacity),
        },
    }

    print()
    print(f"[SERVER_SNAPSHOT] --- RESUMO INFRA ---")
    print(
        f"[SERVER_SNAPSHOT] Recursos totais -> CPU={total_cpu} | MEM={total_memory}"
    )
    print(
        f"[SERVER_SNAPSHOT] Recursos disponíveis -> "
        f"CPU={available_cpu_capacity} ({summary['available_resources']['cpu_pct_of_total']:.2f}% do total) | "
        f"MEM={available_memory_capacity} ({summary['available_resources']['memory_pct_of_total']:.2f}% do total)"
    )
    print(
        f"[SERVER_SNAPSHOT] Recursos indisponíveis -> "
        f"CPU={unavailable_cpu_capacity} ({summary['unavailable_resources']['cpu_pct_of_total']:.2f}% do total) | "
        f"MEM={unavailable_memory_capacity} ({summary['unavailable_resources']['memory_pct_of_total']:.2f}% do total)"
    )
    print(
        f"[SERVER_SNAPSHOT] Consumo total -> "
        f"CPU={total_cpu_demand} ({summary['consumption']['cpu_pct_of_total']:.2f}% do total) | "
        f"MEM={total_memory_demand} ({summary['consumption']['memory_pct_of_total']:.2f}% do total)"
    )
    print(
        f"[SERVER_SNAPSHOT] Consumo dos recursos disponíveis -> "
        f"CPU={available_cpu_demand} ({summary['consumption']['cpu_pct_of_available']:.2f}% dos disponíveis) | "
        f"MEM={available_memory_demand} ({summary['consumption']['memory_pct_of_available']:.2f}% dos disponíveis)"
    )

    return {"snapshot": snapshot, "summary": summary}


# ============================================================================
# MAIN ALGORITHM
# ============================================================================

def trust_edge_v3(parameters: dict = {}):
    """Algoritmo principal que implementa a lógica do TrustEdge V3."""
    
    model = Topology.first().model
    current_step = model.schedule.steps + 1
    model._trust_edge_current_step = current_step
    
    print()
    print()
    print(f"\n[TRUST_EDGE_V3] ===  ⬇️ ⬇️ ⬇️  INÍCIO DO STEP {current_step}  ⬇️ ⬇️ ⬇️  ===")

    # 1. Diagnóstico e monitoramento do downloads de camadas
    diagnose_layer_downloads(current_step)

    # 2. Coleta e resumo dos recursos e demandas dos servidores
    collect_server_resource_snapshot(current_step)

    # 3. Inicializar contadores de provisionamentos e migrações
    if current_step == 0:
        initialize_provisioning_and_migration_tracking()

    # 4. Verificar e desprovisionar serviços inativos e inconsistentes
    check_and_deprovision_inactive_services(current_step)
    
    # 5. Atualizar delays
    update_application_delays(current_step)

    # 6. Processar fila de espera
    process_waiting_queue(current_step)

    # 7. Monitoramento das migrações
    monitor_and_migrate_services(parameters)

    # 8. Provisionamento de novas requisições
    provision_new_requests(current_step)

    # 9. Atuaizar o downtime percebido
    update_user_perceived_downtime_for_current_step(current_step)

    # 10. Coleta de métricas da simulação
    collect_sla_violations_for_current_step()
    collect_infrastructure_metrics_for_current_step()

    # 11. Relatório de provisionamentos e migrações
    if parameters.get("time_steps") == current_step:
        print(f"\n[TRUST_EDGE_V3] Simulação finalizada - coletando métricas finais...\n")
        
        # Coletar métricas auditando todas as operações
        collect_final_provisioning_and_migration_metrics()
        
        # Imprimir resumo consolidado
        print_final_provisioning_and_migration_summary()
        
        # Auditoria de tempos (opcional - para debug)
        # audit_migration_times()


# ============================================================================
# WAITING QUEUE PROCESSING
# ============================================================================

def process_waiting_queue(current_step):
    """Processa a fila de espera tentando provisionar aplicações em servidores disponíveis."""
    
    if not _waiting_queue:
        print()
        print("=" * 70)
        print(f"[DEBUG_WAITING_QUEUE] === FILA DE ESPERA VAZIA - STEP {current_step} ===")
        print("=" * 70)
        return
        
    print()
    print("=" * 70)
    print(f"[DEBUG_WAITING_QUEUE] === PROCESSANDO FILA DE ESPERA - STEP {current_step} ===")
    print(f"[DEBUG_WAITING_QUEUE] {len(_waiting_queue)} aplicações na fila de espera.")
    print("=" * 70)

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
            
        print(f"\n[DEBUG_WAITING_QUEUE] Tentando provisionar aplicação {app.id} da fila:")
        print(f"      Usuário: {user.id}")
        print(f"      Tempo na fila: {current_step - queued_step} steps")
        print(f"      Tempo restante: {remaining_time} steps")
        
        # Tentar provisionar
        if try_provision_service(user, app, service):
            provisioned_items.append(waiting_item)
        else:
            print(f"[DEBUG_WAITING_QUEUE] Aplicação {app.id} ainda não pode ser provisionada")
    
    # Remover itens processados da fila
    for item in provisioned_items:
        _waiting_queue.remove(item)
    
    print(f"[DEBUG_WAITING_QUEUE] {len(provisioned_items)} aplicações processadas")
    print(f"[DEBUG_WAITING_QUEUE] {len(_waiting_queue)} aplicações restantes na fila")
    print(f"[DEBUG_WAITING_QUEUE] === FIM PROCESSAMENTO FILA DE ESPERA ===\n")

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
    current_step = parameters.get("current_step")
    
    reliability_threshold = 0
    delay_threshold = 1
    
    print()
    print("=" * 70)
    print(f"[DEBUG_MONITORING] === MONITORAMENTO E MIGRAÇÃO - STEP {current_step} ===")
    print("=" * 70)
    
    # 2. Verificar migrações em andamento
    check_ongoing_migrations(current_step)
    
    # 3. Identificar novos serviços para migração
    services_to_migrate = identify_services_for_migration(current_step, reliability_threshold, delay_threshold)

    # 4. Processar fila de migração
    process_migration_queue(services_to_migrate, current_step)
    
    print(f"[DEBUG_MONITORING] === FIM MONITORAMENTO E MIGRAÇÃO ===\n")


def check_ongoing_migrations(current_step):
    """
    Verifica e processa TODAS as migrações:
    1. Migrações finalizadas (finished)
    2. Migrações interrompidas (interrupted) - incluindo as marcadas por edge_server_step()
    3. Migrações ativas (em andamento)
    """
    print(f"\n[DEBUG_MONITORING] === VERIFICANDO MIGRAÇÕES - STEP {current_step} ===")
    
    migrations_finished = 0
    migrations_interrupted = 0
    migrations_active = 0
    services_to_requeue = []

    for service in Service.all():
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            continue
            
        migration = service._Service__migrations[-1]
        
        # ═══════════════════════════════════════════════════════════════
        # CASO 1: MIGRAÇÕES MARCADAS PARA CANCELAMENTO (edge_server_step)
        # ═══════════════════════════════════════════════════════════════
        if migration.get("_pending_cancellation") and migration.get("end") is None:
            cancellation_reason = migration.get("_cancellation_reason", "server_failed")
            
            print(f"[DEBUG_MONITORING] 🔴 Migração MARCADA para cancelamento - Serviço {service.id}")
            print(f"                   Razão: {cancellation_reason}")
            
            # Cancelar usando função existente
            if cancel_service_migration(service, reason=cancellation_reason):
                print(f"[DEBUG_MONITORING] ✓ Migração cancelada")
                
                # Limpar flags
                del migration["_pending_cancellation"]
                if "_cancellation_reason" in migration:
                    del migration["_cancellation_reason"]
                
                migrations_interrupted += 1
                
                # Verificar se precisa reprocessar
                app = service.application
                user = app.users[0]
                
                if is_user_accessing_application(user, app, current_step):
                    services_to_requeue.append({
                        "service": service,
                        "app": app,
                        "user": user,
                        "reason": cancellation_reason
                    })
            
            continue  # Pular demais verificações
        
        # ═══════════════════════════════════════════════════════════════
        # CASO 2: MIGRAÇÕES FINALIZADAS NO STEP ATUAL
        # ═══════════════════════════════════════════════════════════════
        if migration["end"] == current_step:
            status = migration.get("status")
            origin = migration.get("origin")
            target = migration.get("target")
            
            if status == "finished":
                migrations_finished += 1
                print(f"[DEBUG_MONITORING] ✅ Migração FINALIZADA - Serviço {service.id}")
                
                # Validar consistência (service_step já atualizou)
                if service.server != target:
                    print(f"[DEBUG_MONITORING] ⚠️ Corrigindo: service.server={service.server.id if service.server else None}, esperado={target.id}")
                    service.server = target
                    if service not in target.services:
                        target.services.append(service)
                
                # Limpar origem
                if origin and service in origin.services:
                    origin.services.remove(service)
                    
            elif status == "interrupted":
                migrations_interrupted += 1
                cause = migration.get("interruption_reason", "unknown")
                print(f"[DEBUG_MONITORING] ⚠️ Migração INTERROMPIDA - Serviço {service.id}")
                print(f"                   Causa: {cause}")
                
                # Verificar se precisa reprocessar
                app = service.application
                user = app.users[0]
                
                if is_user_accessing_application(user, app, current_step):
                    services_to_requeue.append({
                        "service": service,
                        "app": app,
                        "user": user,
                        "reason": cause
                    })
        
        # ═══════════════════════════════════════════════════════════════
        # CASO 3: MIGRAÇÕES AINDA ATIVAS
        # ═══════════════════════════════════════════════════════════════
        elif migration["end"] is None:
            migrations_active += 1

    # ═══════════════════════════════════════════════════════════════
    # REPROCESSAR SERVIÇOS AFETADOS
    # ═══════════════════════════════════════════════════════════════
    if services_to_requeue:
        print(f"\n[DEBUG_MONITORING] Reprocessando {len(services_to_requeue)} serviços afetados:")
        
        for item in services_to_requeue:
            service = item["service"]
            app = item["app"]
            user = item["user"]
            reason = item["reason"]
            
            # Verificar se servidor ainda existe e está disponível
            if service.server and service.server.available:
                print(f"  - Serviço {service.id}: Servidor {service.server.id} OK - não reprocessar")
            else:
                print(f"  - Serviço {service.id}: Sem servidor válido - adicionando à fila (prioridade 999)")
                add_to_waiting_queue(user, app, service, priority_score=999.0)

    # Log resumo
    print(f"\n[DEBUG_MONITORING] Resumo:")
    if migrations_active > 0:
        print(f"  - {migrations_active} migrações ativas")
    if migrations_finished > 0:
        print(f"  - {migrations_finished} migrações finalizadas")
    if migrations_interrupted > 0:
        print(f"  - {migrations_interrupted} migrações interrompidas")
    if len(services_to_requeue) > 0:
        print(f"  - {len(services_to_requeue)} serviços reenfileirados")
    if migrations_active == 0 and migrations_finished == 0 and migrations_interrupted == 0:
        print(f"  - Nenhuma atividade de migração")
    
    print(f"[DEBUG_MONITORING] === FIM VERIFICAÇÃO MIGRAÇÕES ===\n")


def identify_services_for_migration(current_step, reliability_threshold, delay_threshold):
    """Identifica serviços que precisam ser migrados."""
    services_to_migrate = []
    processed_services = set()

    has_active_migration = False
    is_initial_provisioning = False
    
    for user in User.all():
        # ✅ PULAR usuários fazendo nova requisição (provisionamento em andamento)
        if is_making_request(user, current_step):
            continue

        active_applications = get_active_applications_with_remaining_time(user, current_step)
        
        for app_info in active_applications:
            app = app_info["application"]
            service = app.services[0]
            server = service.server

            if service.id in processed_services:
                continue
            processed_services.add(service.id)
            
            # ═════════════════════════════════════════════════════════════
            # PROTEÇÕES CORRIGIDAS
            # ═════════════════════════════════════════════════════════════
            
            # ✅ PROTEÇÃO 1: Detectar provisionamento inicial ou migração ativa
            
            
            if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                last_migration = service._Service__migrations[-1]
                
                if last_migration["end"] is None:  # Processo em andamento
                    has_active_migration = True
                    
                    # Diferenciar: provisionamento inicial vs migração
                    if last_migration.get("origin") is None:
                        is_initial_provisioning = True
                        print(f"[DEBUG] App {app.id} em PROVISIONAMENTO INICIAL - pulando")
                    else:
                        print(f"[DEBUG] App {app.id} em MIGRAÇÃO ATIVA - pulando")
                    
                    continue  # ← Pular ambos os casos
            
            # ✅ PROTEÇÃO 2: Pular se está na fila de espera
            if is_application_in_waiting_queue(app.id):
                print(f"[DEBUG] App {app.id} na fila de espera - pulando")
                continue
            
            # ═════════════════════════════════════════════════════════════
            # AVALIAR CRITÉRIOS DE MIGRAÇÃO
            # ═════════════════════════════════════════════════════════════
            
            # ✅ CASO ESPECIAL: Servidor falhou (MÁXIMA PRIORIDADE)
            # Neste caso, delay = inf MAS NÃO tem migração ativa
            if server and not server.available:
                print(f"[DEBUG] App {app.id}: Servidor {server.id} FALHOU - MIGRAÇÃO URGENTE")
                services_to_migrate.append({
                    "service": service,
                    "application": app,
                    "user": user,
                    "current_server": server,
                    "reason": "server_failed",
                    "priority": 0,  # ← Prioridade 0 = MÁXIMA
                    "remaining_access_time": app_info["remaining_time"],
                    "criteria_data": {
                        "needs_migration": True,
                        "reason": "server_failed",
                        "priority": 0
                    }
                })
                continue  # ← Pular demais verificações
            
            # ✅ Servidor deve estar disponível para avaliar outros critérios
            if not server:
                print(f"[DEBUG] App {app.id} sem servidor - pulando avaliação")
                continue
            
            # ✅ Delay deve ser válido para avaliar violação
            current_delay = user.delays.get(str(app.id))
            
            if not has_active_migration:
                if current_delay is None or current_delay == float('inf'):
                    # Se chegou aqui com delay infinito, algo está errado
                    # (servidor disponível MAS delay infinito = inconsistência)
                    print(f"[DEBUG] App {app.id}: INCONSISTÊNCIA detectada!")
                    print(f"        Servidor: {server.id} (available={server.available})")
                    print(f"        Delay: {current_delay}")
                    print(f"        Service._available: {service._available}")
                    continue
            
            # ✅ AVALIAÇÃO NORMAL: delay e confiabilidade
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
    
    # ✅ VERIFICAR SE SERVIÇO ESTÁ EM PROVISIONAMENTO INICIAL
    # if is_making_request(user, current_step):
    #     print(f"[DEBUG] Serviço {service.id} em provisionamento inicial - não avaliar migração")
    #     return {"needs_migration": False}
    # if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
    #     last_migration = service._Service__migrations[-1]
        
    #     # Se migração está ativa E é provisionamento inicial (origin = None)
    #     if last_migration["end"] is None and last_migration.get("origin") is None:
    #         print(f"[DEBUG] Serviço {service.id} em provisionamento inicial - não avaliar migração")
    #         return {"needs_migration": False}
    
    # # ✅ 1. Servidor em falha
    # if server and not server.available:
    #     print(f"[DEBUG] Serviço {service.id} no servidor {server.id} que falhou")
    #     return {
    #         "needs_migration": True,
    #         "reason": "server_failed",
    #         "priority": 1
    #     }
    
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
        print(f"[DEBUG_MONITORING] Nenhum serviço precisa ser migrado")
        return
    
    # Ordenar por prioridade e urgência
    services_to_migrate.sort(key=lambda s: (
        s["priority"],
        -s["criteria_data"].get("delay_violation_ratio", 0),
        s["criteria_data"].get("conditional_reliability", 100)
    ))
    
    print(f"[DEBUG_MONITORING] Processando {len(services_to_migrate)} serviços para migração")
    
    for service_metadata in services_to_migrate:
        service = service_metadata["service"]
        app = service_metadata["application"]
        user = service_metadata["user"]
        current_server = service_metadata["current_server"]
        reason = service_metadata["reason"]
        
        print(f"\n[DEBUG_MONITORING] Migrando serviço {service.id} - Razão: {reason}")
        
        if (not current_server):
            print(f"[DEBUG_MONITORING] Servidor atual: NENHUM (Servidor falhou)")
        else:
            print(f"[DEBUG_MONITORING] Servidor atual: {current_server.id} (Status: {current_server.status})")

        # Encontrar servidor de destino
        target_server = find_migration_target(user, service, current_server, reason)
        
        if target_server and target_server.available:
            if initiate_service_migration(service, target_server, reason, current_step):
               pass
        else:
            if not current_server or not current_server.available:
                # Servidor falhou E não há alternativa - DESPROVISIONAMENTO
                print(f"[LOG] Servidor atual falhou e sem alternativas - movendo ou mantendo na fila de espera")
               
               # Adicionar à fila de espera com alta prioridade (falha de servidor)
                priority_score = 999.0  # Prioridade máxima para falhas de servidor
                add_to_waiting_queue(user, app, service, priority_score)
     
            else:
                print(f"[DEBUG_MONITORING] Sem servidor disponível - mantendo no servidor atual {current_server.id}")

def find_migration_target(user, service, current_server, migration_reason):
    """Encontra o melhor servidor de destino para migração."""
    available_servers = get_host_candidates(user,service)
    
    if not available_servers:
        return None
    
    origin_server_id = None

    if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
        last_migration = service._Service__migrations[-1]
        origin = last_migration.get("origin")
        if origin:
            origin_server_id = origin.id
    
    # Filtrar candidatos (excluir origem real)
    migration_candidates = [
        candidate for candidate in available_servers
        if not origin_server_id or candidate["object"].id != origin_server_id
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
        else:
            return None


def initiate_service_migration(service, target_server, reason, current_step):
    """Inicia migração com relacionamentos antecipados."""
    
    # ✅ DEBUG IMEDIATO
    print(f"\n[INITIATE_MIGRATION] === INÍCIO ===")
    print(f"[INITIATE_MIGRATION] Serviço: {service.id}")
    print(f"[INITIATE_MIGRATION] Target: {target_server.id}")
    print(f"[INITIATE_MIGRATION] Reason: '{reason}'")
    print(f"[INITIATE_MIGRATION] Current Step: {current_step}")
    
    # ✅ SALVAR servidor original ANTES de qualquer alteração
    original_server = service.server
    
    if original_server:
        print(f"[INITIATE_MIGRATION] Original Server: {original_server.id} (available: {original_server.available})")
    else:
        print(f"[INITIATE_MIGRATION] Original Server: None (provisionamento inicial)")
    
    try:
        # ✅ 1. CHAMAR provision() PRIMEIRO (isso cria a migração)
        print(f"[INITIATE_MIGRATION] Chamando service.provision()...")
        service.provision(target_server=target_server)
        print(f"[INITIATE_MIGRATION] provision() executado")
        
        # ✅ 2. VERIFICAR se migração foi criada
        if not hasattr(service, '_Service__migrations'):
            print(f"[INITIATE_MIGRATION] ✗ ERRO: Serviço não tem atributo __migrations!")
            return False
        
        if len(service._Service__migrations) == 0:
            print(f"[INITIATE_MIGRATION] ✗ ERRO: Lista de migrações está vazia!")
            return False
        
        print(f"[INITIATE_MIGRATION] Total de migrações: {len(service._Service__migrations)}")
        
        # ✅ 3. Pegar migração recém-criada
        migration = service._Service__migrations[-1]
        
        print(f"[INITIATE_MIGRATION] Migração antes de adicionar flags:")
        print(f"                     Status: {migration.get('status', 'N/A')}")
        print(f"                     Origin: {migration.get('origin').id if migration.get('origin') else None}")
        print(f"                     Target: {migration.get('target').id if migration.get('target') else None}")
        print(f"                     migration_reason (antes): {migration.get('migration_reason', 'N/A')}")
        
        # ✅ 4. ADICIONAR migration_reason (SEMPRE - seja nova ou não)
        migration["migration_reason"] = reason
        migration["relationships_created_by_algorithm"] = True
        migration["origin_cleanup_pending"] = True
        
        print(f"[INITIATE_MIGRATION] Flags adicionadas:")
        print(f"                     migration_reason (depois): '{migration['migration_reason']}'")
        print(f"                     relationships_created_by_algorithm: {migration['relationships_created_by_algorithm']}")
        
        # ✅ 5. DEPOIS criar relacionamentos SOMENTE NO DESTINO
        service.server = target_server
        if service not in target_server.services:
            target_server.services.append(service)
        
        # ✅ 6. Marcar como INDISPONÍVEL
        service._available = False
        
        print(f"[INITIATE_MIGRATION] ✓ Migração registrada com sucesso")
        print(f"[INITIATE_MIGRATION] === FIM ===\n")
        
        return True
        
    except Exception as e:
        print(f"[INITIATE_MIGRATION] ✗ ERRO EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        
        # Reverter APENAS destino
        service.server = original_server
        if service in target_server.services:
            target_server.services.remove(service)
        
        return False


def update_application_delays(current_step):
    """Atualiza delays considerando disponibilidade REAL."""
    
    print()
    print("=" * 70)
    print(f"[DEBUG_DELAYS] === ATUALIZANDO DELAYS - STEP {current_step} ===")
    print("=" * 70)
    
    for user in User.all():
        if is_making_request(user, current_step):
            continue
        
        for app in user.applications:
            service = app.services[0]
            
            if not is_user_accessing_application(user, app, current_step):
                user.delays[str(app.id)] = 0
                continue
            
            # ✅ VERIFICAÇÃO CRÍTICA: service._available é a FLAG MESTRE
            if not service._available:
                user.delays[str(app.id)] = float('inf')
                print(f"[DEBUG_DELAYS] App {app.id}: INDISPONÍVEL (_available=False) - Delay = inf")
                
                # Debug adicional
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    last_migration = service._Service__migrations[-1]
                    if last_migration["end"] is None:
                        print(f"        Status migração: {last_migration.get('status', 'unknown')}")
                
                continue
            
            # ✅ Verificações adicionais
            if not service.server or service.server.status != "available":
                user.delays[str(app.id)] = float('inf')
                print(f"[DEBUG_DELAYS] App {app.id}: INDISPONÍVEL (servidor indisponível) - Delay = inf")
                continue
            
            # ✅ Serviço realmente disponível - calcular delay
            user.set_communication_path(app=app)
            new_delay = user._compute_delay(app=app, metric="latency")
            user.delays[str(app.id)] = new_delay
            print(f"[DEBUG_DELAYS] App {app.id}: DISPONÍVEL - Delay = {new_delay}")


def check_service_availability_after_service_step(service):
    """
    Verifica disponibilidade REAL do serviço APÓS service_step() executar.
    
    REGRAS:
    1. Se NÃO tem migração: disponível SE server.available E service._available
    2. Se TEM migração ativa (end=None): INDISPONÍVEL
    3. Se migração finalizou (end!=None) NO STEP ANTERIOR: DISPONÍVEL
    4. Se migração finalizou NO STEP ATUAL: AINDA INDISPONÍVEL
    
    Returns:
        bool: True se disponível, False caso contrário
    """
    
    # Caso 1: Sem migração
    if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
        return service.server and service.server.status == "available" and service._available
    
    last_migration = service._Service__migrations[-1]
    
    # Caso 2: Migração ativa
    if last_migration["end"] is None:
        return False  # INDISPONÍVEL
    
    # Caso 3 e 4: Migração finalizada
    current_step = service.model.schedule.steps + 1
    migration_ended_at = last_migration["end"]
    
    # Se finalizou no step atual, service_step() ACABOU DE FINALIZAR
    # Mas delays só devem ser atualizados NO PRÓXIMO STEP
    if migration_ended_at == current_step:
        return False  # AINDA INDISPONÍVEL (acabou de finalizar)
    
    # Se finalizou em step anterior, agora está disponível
    return service.server and service.server.status == "available" and service._available


def check_and_deprovision_inactive_services(current_step):
    """
    Verifica e desprovisiona serviços inativos.
    TAMBÉM limpa serviços órfãos e recalcula demanda dos servidores.
    """
    print()
    print("=" * 70)
    print(f"[DEBUG_DEPROVISION] === VERIFICANDO SERVIÇOS INATIVOS E ÓRFÃOS - STEP {current_step} ===")
    print("=" * 70)
    
    services_to_deprovision = []
    orphans_cleaned = 0
    servers_to_recalculate = set()  # ✅ NOVO: rastrear servidores que precisam recalcular demanda
    
    # ═══════════════════════════════════════════════════════════════
    # PARTE 1: LIMPAR SERVIÇOS ÓRFÃOS DE TODOS OS SERVIDORES
    # ═══════════════════════════════════════════════════════════════
    for server in EdgeServer.all():
        services_to_remove = []
        
        for service in list(server.services):
            should_remove = False
            removal_reason = ""
            
            # Caso 1: Serviço aponta para OUTRO servidor
            if service.server and service.server != server:
                should_remove = True
                removal_reason = f"aponta para servidor {service.server.id}"
            
            # Caso 2: Serviço sem aplicação ou usuário
            elif not service.application or not service.application.users:
                should_remove = True
                removal_reason = "sem aplicação/usuário válido"
            
            # Caso 3: Servidor disponível MAS recursos zerados E tem serviços
            elif (server.available and 
                  server.cpu_demand == 0 and 
                  server.memory_demand == 0 and 
                  len(server.services) > 0):
                should_remove = True
                removal_reason = "servidor disponível mas recursos zerados"
            
            # Caso 4: Servidor indisponível E serviço não está em migração ativa
            elif not server.available and service.server == server:
                in_active_migration = False
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    last_migration = service._Service__migrations[-1]
                    if last_migration.get("end") is None:
                        in_active_migration = True
                
                if not in_active_migration:
                    should_remove = True
                    removal_reason = f"servidor {server.id} indisponível sem migração ativa"
            
            if should_remove:
                services_to_remove.append((service, removal_reason))
        
        # Executar remoção de órfãos
        for service, reason in services_to_remove:
            server.services.remove(service)
            orphans_cleaned += 1
            
            # ✅ MARCAR servidor para recalcular demanda
            servers_to_recalculate.add(server)
            
            if orphans_cleaned <= 5:
                print(f"[DEBUG_DEPROVISION] Servidor {server.id}: Removido órfão {service.id} ({reason})")
    
    if orphans_cleaned > 0:
        print(f"[DEBUG_DEPROVISION] {orphans_cleaned} serviços órfãos removidos")
    
    # ═══════════════════════════════════════════════════════════════
    # ✅ NOVO: RECALCULAR DEMANDA DOS SERVIDORES AFETADOS
    # ═══════════════════════════════════════════════════════════════
    for server in servers_to_recalculate:
        # Recalcular demanda a partir dos serviços reais
        correct_cpu_demand = sum(s.cpu_demand for s in server.services if s.server == server)
        correct_memory_demand = sum(s.memory_demand for s in server.services if s.server == server)
        
        if server.cpu_demand != correct_cpu_demand or server.memory_demand != correct_memory_demand:
            print(f"[DEBUG_DEPROVISION] Servidor {server.id}: Recalculando demanda")
            print(f"                    CPU: {server.cpu_demand} → {correct_cpu_demand}")
            print(f"                    MEM: {server.memory_demand} → {correct_memory_demand}")
            
            server.cpu_demand = correct_cpu_demand
            server.memory_demand = correct_memory_demand
    
    # ═══════════════════════════════════════════════════════════════
    # PARTE 2: IDENTIFICAR SERVIÇOS INATIVOS PARA DESPROVISIONAMENTO
    # ═══════════════════════════════════════════════════════════════
    for service in Service.all():
        app = service.application
        
        if not app or not app.users:
            continue
        
        user = app.users[0]
        app_id = str(app.id)
        
        is_accessing = is_user_accessing_application(user, app, current_step)
        
        if not is_accessing and service.server:
            server = service.server
            
            # PROTEÇÃO: Servidor falhou e relacionamento já limpo
            if not server.available and service not in server.services:
                print(f"[DEBUG_DEPROVISION] Serviço {service.id}: Servidor {server.id} falhou - limpeza completa")
                
                service.server = None
                service._available = False
                user.delays[app_id] = 0
                
                # ✅ NÃO precisa ajustar demanda aqui porque já foi recalculada acima
                
                # Limpar migração pendente
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    last_migration = service._Service__migrations[-1]
                    if last_migration.get("end") is None:
                        cancel_service_migration(service, reason="server_failed_and_user_stopped")
                
                continue
            
            services_to_deprovision.append({
                "service": service,
                "app": app,
                "server": server,
                "has_active_migration": (hasattr(service, '_Service__migrations') and 
                                        len(service._Service__migrations) > 0 and
                                        service._Service__migrations[-1].get("end") is None)
            })
    
    if not services_to_deprovision:
        if orphans_cleaned == 0:
            print(f"[DEBUG_DEPROVISION] Nenhum serviço inativo ou órfão para processar")
        print(f"[DEBUG_DEPROVISION] === FIM VERIFICAÇÃO ===\n")
        return
    
    print(f"[DEBUG_DEPROVISION] {len(services_to_deprovision)} serviços inativos identificados")
    
    # ═══════════════════════════════════════════════════════════════
    # ETAPA 1: CANCELAR MIGRAÇÕES ATIVAS
    # ═══════════════════════════════════════════════════════════════
    migrations_cancelled = 0
    for item in services_to_deprovision:
        if item["has_active_migration"]:
            if cancel_service_migration(item["service"], reason="user_stopped_accessing"):
                migrations_cancelled += 1
    
    if migrations_cancelled > 0:
        print(f"[DEBUG_DEPROVISION] {migrations_cancelled} migrações canceladas")
        print(f"[DEBUG_DEPROVISION] Desprovisionamento será feito no próximo step")
        print(f"[DEBUG_DEPROVISION] === FIM VERIFICAÇÃO ===\n")
        return
    
    # ═══════════════════════════════════════════════════════════════
    # ETAPA 2: DESPROVISIONAR SERVIÇOS
    # ═══════════════════════════════════════════════════════════════
    deprovisioned_count = 0
    for item in services_to_deprovision:
        service = item["service"]
        app = item["app"]
        server = item["server"]
        user = app.users[0]
        
        print(f"\n[DEBUG_DEPROVISION] Serviço {service.id} (App {app.id}) - desprovisionando")
        print(f"[DEPROVISION] Desprovisionando serviço {service.id} do servidor {server.id}")
        
        # VERIFICAÇÃO: Se ainda tem migração ativa (anomalia)
        if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
            last_migration = service._Service__migrations[-1]
            
            if last_migration.get("end") is None:
                print(f"[DEPROVISION] ⚠️ ANOMALIA: Migração ativa - cancelando antes de desprovisionar")
                cancel_service_migration(service, reason="user_stopped_accessing")
        
        # Liberar recursos SOMENTE se servidor está disponível
        if server.available:
            server.cpu_demand = max(0, server.cpu_demand - service.cpu_demand)
            server.memory_demand = max(0, server.memory_demand - service.memory_demand)
            print(f"[DEPROVISION] Recursos liberados")
        else:
            print(f"[DEPROVISION] Recursos NÃO liberados (servidor indisponível)")
        
        # Remover serviço da lista do servidor
        if service in server.services:
            server.services.remove(service)
            print(f"[DEPROVISION] ✓ Removido da lista do servidor {server.id}")
        
        # Limpar relacionamento
        service.server = None
        service._available = False
        
        # Limpar delay do usuário
        app_id = str(app.id)
        user.delays[app_id] = 0
        
        print(f"[DEPROVISION] ✓ Desprovisionamento concluído")
        deprovisioned_count += 1
    
    print(f"[DEBUG_DEPROVISION] {deprovisioned_count} serviços desprovisionados")
    print(f"[DEBUG_DEPROVISION] === FIM VERIFICAÇÃO ===\n")


def cancel_service_migration(service, reason):
    """
    Cancela uma migração em andamento e interrompe downloads relacionados.
    """
    if not hasattr(service, '_Service__migrations') or not service._Service__migrations:
        return False
    
    migration = service._Service__migrations[-1]
    
    if migration.get("end") is not None:
        return False
    
    current_step = service.model.schedule.steps + 1
    target_server = migration.get("target")
    
    print(f"[CANCEL_MIGRATION] Cancelando migração do serviço {service.id}")
    print(f"                   Razão: {reason}")
    print(f"                   Target: {target_server.id if target_server else 'None'}")
    
    # ✅ OBTER IMAGEM DO SERVIÇO
    service_image = None
    if hasattr(service, 'image_digest') and service.image_digest:
        from edge_sim_py.components.container_image import ContainerImage
        service_image = ContainerImage.find_by(attribute_name="digest", attribute_value=service.image_digest)
    
    interrupted_flows = []
    layers_to_remove = []
    
    if target_server and service_image:
        # ✅ 1. INTERROMPER FLUXOS NA download_queue
        for flow in list(target_server.download_queue):
            if (hasattr(flow, 'metadata') and 
                flow.metadata.get('type') == 'layer' and
                flow.target == target_server):
                
                layer = flow.metadata.get('object')
                
                if layer and hasattr(layer, 'digest') and layer.digest in service_image.layers_digests:
                    flow.status = "interrupted"
                    flow.data_to_transfer = 0
                    interrupted_flows.append(flow)
                    print(f"[CANCEL_MIGRATION] ✓ Fluxo interrompido: Layer {layer.digest[:8]}")
        
        # ✅ 2. LIMPAR waiting_queue
        for layer in list(target_server.waiting_queue):
            if hasattr(layer, 'digest') and layer.digest in service_image.layers_digests:
                layers_to_remove.append(layer)
        
        for layer in layers_to_remove:
            target_server.waiting_queue.remove(layer)
            print(f"[CANCEL_MIGRATION] ✓ Camada removida da waiting_queue: {layer.digest[:8]}")
    
    # ✅ 3. LIMPAR FLUXOS INTERROMPIDOS DA download_queue
    if target_server:
        for flow in interrupted_flows:
            if flow in target_server.download_queue:
                target_server.download_queue.remove(flow)
                print(f"[CANCEL_MIGRATION] ✓ Fluxo removido da download_queue")
    
    print(f"[CANCEL_MIGRATION] Total de fluxos interrompidos e removidos: {len(interrupted_flows)}")
    print(f"[CANCEL_MIGRATION] Camadas removidas da waiting_queue: {len(layers_to_remove)}")
    
    # 4. Marcar migração como interrompida
    migration["status"] = "interrupted"
    migration["end"] = current_step
    migration["interruption_reason"] = reason
    
    # 5. Resetar flags de controle
    service.being_provisioned = False
    
    # 6. Decrementar contadores de migração
    if target_server and hasattr(target_server, 'ongoing_migrations'):
        target_server.ongoing_migrations = max(0, target_server.ongoing_migrations - 1)
    
    origin_server = migration.get("origin")
    if origin_server and hasattr(origin_server, 'ongoing_migrations'):
        origin_server.ongoing_migrations = max(0, origin_server.ongoing_migrations - 1)
    
    print(f"[CANCEL_MIGRATION] ✓ Migração cancelada com sucesso")
    return True

# ============================================================================
# NEW REQUEST PROVISIONING
# ============================================================================

def provision_new_requests(current_step):
    """Provisiona novas requisições de aplicações."""
    print()
    print("=" * 70)
    print(f"[DEBUG_NEW_REQUESTS] === PROVISIONAMENTO DE NOVAS REQUISIÇÕES - STEP {current_step} ===")
    print("=" * 70)
    
    # Coletar aplicações com novas requisições
    apps_metadata = collect_new_request_metadata(current_step)
    
    if apps_metadata:
        print(f"[DEBUG_NEW_REQUESTS] {len(apps_metadata)} aplicações com novas requisições")
        
        # Ordenar por prioridade
        apps_metadata = sort_applications_by_priority(apps_metadata)
        
        # Processar cada aplicação
        for app_metadata in apps_metadata:
            process_application_request(app_metadata, apps_metadata)
    else:
        print(f"[DEBUG_NEW_REQUESTS] Nenhuma nova requisição no step {current_step}")
    
    print(f"[DEBUG_NEW_REQUESTS] === FIM PROVISIONAMENTO DE NOVAS REQUISIÇÕES ===\n")

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
    # if service.server:
    #     print(f"[LOG] Serviço já hospedado no servidor {service.server.id}")
    #     return
    
    # Verificar se está na fila de espera
    if is_application_in_waiting_queue(app.id):
        print(f"[LOG] Aplicação {app.id} já está na fila de espera")
        return
    
    # Tentar provisionar
    if not try_provision_service(user, app, service):
        # Adicionar à fila de espera se falhou
        #min_and_max_app = find_minimum_and_maximum(metadata=all_apps_metadata)
        print(f"[LOG] Adicionando aplicação {app.id} à fila de espera")
        priority_score = app_metadata["delay_urgency"]
        add_to_waiting_queue(user, app, service, priority_score)

def try_provision_service(user, app, service):
    """Tenta provisionar um serviço com relacionamentos antecipados."""
    
    edge_servers = get_host_candidates(user=user, service=service)
    
    if not edge_servers:
        print(f"[LOG] Nenhum servidor disponível para aplicação {app.id}")
        return False
    
    edge_servers = sort_host_candidates(edge_servers)
    
    for edge_server_metadata in edge_servers:
        edge_server = edge_server_metadata["object"]
        
        if edge_server.has_capacity_to_host(service):
            print(f"[LOG] ✓ Provisionando aplicação {app.id} no servidor {edge_server.id}")
            print(f"      Delay previsto: {edge_server_metadata['overall_delay']}")
            print(f"      SLA: {user.delay_slas[str(app.id)]}")
            print(f"      Viola SLA: {'SIM' if edge_server_metadata['sla_violations'] else 'NÃO'}")
            
            # ✅ SALVAR estado original
            original_server = service.server
            
            try:
                # ✅ CHAMAR provision() PRIMEIRO
                service.provision(target_server=edge_server)
                
                # ✅ DEPOIS criar relacionamentos antecipados
                service.server = edge_server
                edge_server.services.append(service)
                
                # ✅ Marcar como INDISPONÍVEL
                service._available = False
                
                # ✅ ADICIONAR flags
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    migration = service._Service__migrations[-1]
                    migration["relationships_created_by_algorithm"] = True
                    migration["is_initial_provisioning"] = True
                    
                    print(f"[LOG] Provisionamento iniciado - Origin: {migration['origin'].id if migration['origin'] else 'None'}, Target: {migration['target'].id}")
                
                return True
                
            except Exception as e:
                print(f"[LOG] ✗ Erro ao provisionar: {e}")
                import traceback
                traceback.print_exc()
                
                # Reverter
                service.server = original_server
                if service in edge_server.services:
                    edge_server.services.remove(service)
                
                # Tentar próximo servidor
                continue
    
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