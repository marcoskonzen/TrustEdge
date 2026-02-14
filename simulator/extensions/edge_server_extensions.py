"""This module contains the edge server extensions with decoupled execution."""

# Importing EdgeSimPy components
from edge_sim_py.components.container_registry import ContainerRegistry
from edge_sim_py.components.network_flow import NetworkFlow
from edge_sim_py.components.service import Service
from edge_sim_py.components.edge_server import EdgeServer

# Importing Python modules
import networkx as nx
from random import randint


# ═══════════════════════════════════════════════════════════════
# ✅ OTIMIZAÇÃO: Índice Reverso de Camadas
# ═══════════════════════════════════════════════════════════════

_LAYER_INDEX = {}  # {layer_digest: [server_ids]}
_LAYER_INDEX_LAST_UPDATE = 0

def _rebuild_layer_index(current_step):
    """
    Reconstrói índice reverso de camadas.
    Executado apenas quando há mudanças (novo download completo).
    """
    global _LAYER_INDEX, _LAYER_INDEX_LAST_UPDATE
    
    # ✅ Reconstruir a cada 5 steps (downloads podem ter terminado)
    if current_step - _LAYER_INDEX_LAST_UPDATE < 5:
        return
    
    _LAYER_INDEX = {}
    
    # Indexar todas as camadas de todos os servidores
    for server in EdgeServer.all():
        if not server.available:
            continue
        
        for layer in server.container_layers:
            digest = layer.digest
            
            if digest not in _LAYER_INDEX:
                _LAYER_INDEX[digest] = []
            
            _LAYER_INDEX[digest].append(server.id)
    
    _LAYER_INDEX_LAST_UPDATE = current_step
    
    # Debug
    total_layers_indexed = len(_LAYER_INDEX)
    avg_servers_per_layer = sum(len(servers) for servers in _LAYER_INDEX.values()) / total_layers_indexed if total_layers_indexed > 0 else 0
    print(f"[LAYER_INDEX] Índice reconstruído: {total_layers_indexed} camadas únicas, {avg_servers_per_layer:.1f} servidores/camada em média")


def get_layer_download_config():
    """Retorna a configuração atual de download."""
    return _LAYER_DOWNLOAD_CONFIG.copy()

# ═══════════════════════════════════════════════════════════════
# ✅ CONFIGURATION FLAGS (Global - set by algorithm)
# ═══════════════════════════════════════════════════════════════

_LAYER_DOWNLOAD_CONFIG = {
    "enable_p2p": True,           # Se False, baixa apenas de Registries
    "enable_registry": True,      # Se False, baixa apenas de Edge Servers (P2P puro)
}

def configure_layer_download_strategy(enable_p2p=True, enable_registry=True):
    """
    Configura a estratégia de download de camadas.
    
    Args:
        enable_p2p: Permite download de outros Edge Servers (P2P)
        enable_registry: Permite download de Container Registries
    """
    global _LAYER_DOWNLOAD_CONFIG
    _LAYER_DOWNLOAD_CONFIG["enable_p2p"] = enable_p2p
    _LAYER_DOWNLOAD_CONFIG["enable_registry"] = enable_registry
    
    print(f"[LAYER_CONFIG] Download strategy configured:")
    print(f"               - P2P (Edge Servers): {'ENABLED' if enable_p2p else 'DISABLED'}")
    print(f"               - Registry: {'ENABLED' if enable_registry else 'DISABLED'}")


def get_layer_download_config():
    """Retorna a configuração atual de download."""
    return _LAYER_DOWNLOAD_CONFIG.copy()


# ═══════════════════════════════════════════════════════════════
# ✅ EXECUTORES DESACOPLADOS
# ═══════════════════════════════════════════════════════════════

class FailureManagementExecutor:
    """Gerencia apenas a lógica de falhas do servidor."""
    
    def __init__(self, server):
        self.server = server
        self.current_step = server.model.schedule.steps + 1
    
    def should_generate_new_failure_set(self):
        """Verifica se deve gerar novo conjunto de falhas."""
        no_failure_has_occurred = len(self.server.failure_model.failure_history) == 0
        
        if no_failure_has_occurred:
            return True
        
        last_failure_that_occurred_is_the_last_planned = (
            self.server.failure_model.failure_history[-1] == 
            self.server.failure_model.failure_trace[-1][-1]
        )
        
        return last_failure_that_occurred_is_the_last_planned
    
    def generate_failure_set(self):
        """Gera novo conjunto de falhas."""
        interval_between_sets = randint(
            a=self.server.failure_model.failure_characteristics["interval_between_sets"]["lower_bound"],
            b=self.server.failure_model.failure_characteristics["interval_between_sets"]["upper_bound"],
        )
        next_failure_time_step = (
            self.server.failure_model.failure_trace[-1][-1]["becomes_available_at"] + 
            interval_between_sets
        )
        self.server.failure_model.generate_failure_set(next_failure_time_step=next_failure_time_step)
    
    def get_ongoing_failure(self):
        """Retorna a falha em curso (se houver)."""
        flatten_failure_trace = [
            item for failure_group in self.server.failure_model.failure_trace 
            for item in failure_group
        ]
        
        return next(
            (
                failure for failure in flatten_failure_trace
                if failure["failure_starts_at"] <= self.current_step <= failure["becomes_available_at"]
            ),
            None,
        )
    
    def update_server_status(self, ongoing_failure):
        """Atualiza o status do servidor baseado na falha em curso."""
        if ongoing_failure is None:
            self.server.status = "available"
            self.server.available = True
            return
        
        # Transição: available → failing
        if (self.server.status == "available" and 
            self.current_step >= ongoing_failure["failure_starts_at"] and 
            self.current_step < ongoing_failure["starts_booting_at"]):
            self.server.status = "failing"
            self.server.available = False
        
        # Transição: failing → booting
        elif (self.server.status == "failing" and 
              self.current_step >= ongoing_failure["starts_booting_at"] and 
              self.current_step < ongoing_failure["becomes_available_at"]):
            self.server.status = "booting"
            self.server.available = False
        
        # Transição: booting → available
        elif (self.server.status == "booting" and 
              self.current_step >= ongoing_failure["becomes_available_at"]):
            self.server.status = "available"
            self.server.available = True
            if ongoing_failure not in self.server.failure_model.failure_history:
                self.server.failure_model.failure_history.append(ongoing_failure)
    
    def update_services_availability(self):
        """Atualiza disponibilidade dos serviços baseado no status do servidor."""
        if self.server.status == "available":
            for service in self.server.services:
                if not service.being_provisioned:
                    service._available = True
        else:
            for service in list(self.server.services):
                service._available = False


class FailureInterruptionExecutor:
    """Gerencia interrupções causadas por falhas."""
    
    def __init__(self, server):
        self.server = server
    
    def clear_waiting_queue(self):
        """Limpa a fila de espera."""
        self.server.waiting_queue = []
    
    def interrupt_downloads(self):
        """Interrompe todos os downloads em andamento."""
        for flow in self.server.download_queue:
            flow.data_to_transfer = 0
            flow.status = "interrupted"
    
    def mark_migrations_for_cancellation(self):
        """Marca migrações que têm este servidor como destino para cancelamento."""
        for service in Service.all():
            if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
                continue
            
            migration = service._Service__migrations[-1]
            
            # Pular migrações já finalizadas
            if migration.get("end") is not None:
                continue
            
            target = migration.get("target")
            
            # Se este servidor é DESTINO da migração → Marcar para cancelamento
            if target == self.server:
                migration["_pending_cancellation"] = True
                migration["_cancellation_reason"] = "target_server_failed"
                print(f"[EDGE_SERVER] Migração do serviço {service.id} MARCADA para cancelamento (target falhou)")
    
    def reset_resource_demands(self):
        """Zera demandas de recursos do servidor."""
        self.server.cpu_demand = 0
        self.server.memory_demand = 0


class LayerProvisioningExecutor:
    """Gerencia o provisionamento de camadas de container."""
    
    def __init__(self, server):
        self.server = server
        self.config = get_layer_download_config()
        
        # ✅ Cache de caminhos
        if not hasattr(server, '_path_cache'):
            server._path_cache = {}
    
    def can_start_new_download(self):
        """Verifica se pode iniciar novo download."""
        return (len(self.server.waiting_queue) > 0 and 
                len(self.server.download_queue) < self.server.max_concurrent_layer_downloads)
    
    def find_layer_sources(self, layer):
        """
        ✅ OTIMIZAÇÃO: Usa índice reverso e cache de IDs para identificar fontes.
        Garante que o Registry seja sempre considerado se configurado.
        """
        # ✅ Garantir que índice está atualizado
        current_step = self.server.model.schedule.steps + 1
        _rebuild_layer_index(current_step)
        
        candidates = []
        
        # ✅ Lookup direto no índice
        server_ids_with_layer = _LAYER_INDEX.get(layer.digest, [])
        
        if not server_ids_with_layer:
            return candidates  # Camada não encontrada
        
        # ✅ OTIMIZAÇÃO: Cache de IDs de Registry (Lookup O(1))
        # Identifica quais IDs de servidor pertencem a Registries
        registry_server_ids = {
            reg.server.id for reg in ContainerRegistry.all() 
            if hasattr(reg, 'server') and reg.server
        }
        
        # Cache local de servidores para evitar buscas repetidas
        all_servers_map = {s.id: s for s in EdgeServer.all()}
        
        # Filtrar por tipo (Registry vs P2P) e disponibilidade
        for server_id in server_ids_with_layer:
            # Pular o próprio servidor
            if server_id == self.server.id:
                continue
            
            # Obter objeto do servidor via map (rápido)
            server = all_servers_map.get(server_id)
            
            if not server or not server.available:
                continue
            
            # ✅ Verificar se é Registry
            is_registry_server = server_id in registry_server_ids
            
            # Adicionar candidato respeitando a configuração
            if is_registry_server:
                if self.config["enable_registry"]:
                    candidates.append(server)
            else:
                if self.config["enable_p2p"]:
                    candidates.append(server)
        
        return candidates
    
    def calculate_paths_to_sources(self, sources):
        """
        ✅ OTIMIZAÇÃO: Calcula caminhos usando CACHE.
        Cache persiste durante toda a simulação (topologia não muda).
        """
        candidates_with_path = []
        topology = self.server.model.topology
        target_switch = self.server.base_station.network_switch
        
        for source_server in sources:
            source_switch = source_server.base_station.network_switch
            
            # ✅ Chave de cache: Par ordenado de switches
            cache_key = (source_switch.id, target_switch.id)
            
            # Verificar cache primeiro
            if cache_key in self.server._path_cache:
                path = self.server._path_cache[cache_key]
                candidates_with_path.append({"server": source_server, "path": path})
                continue
            
            # Se não está no cache, calcular e armazenar
            try:
                path = nx.shortest_path(
                    G=topology,
                    source=source_switch,
                    target=target_switch,
                )
                
                # ✅ Armazenar no cache (permanente durante simulação)
                self.server._path_cache[cache_key] = path
                
                candidates_with_path.append({"server": source_server, "path": path})
            except nx.NetworkXNoPath:
                # ✅ Também cachear "sem caminho" (evita recálculo)
                self.server._path_cache[cache_key] = None
                continue
        
        return candidates_with_path
    
    def select_best_source(self, candidates_with_path):
        """
        Seleciona a melhor fonte baseando-se no TEMPO ESTIMADO de download,
        considerando:
        - Largura de banda do caminho
        - Latência acumulada
        - Carga atual do servidor fonte
        """
        if not candidates_with_path:
            return None
        
        # ✅ NOVO: Calcular tempo estimado para cada candidato
        from simulator.helper_functions import _estimate_download_time_from_source
        
        for candidate in candidates_with_path:
            # Pegar a camada que está sendo baixada (contexto do executor)
            # Simplificação: assumir que o tamanho médio é representativo
            # (Idealmente, receber a camada como parâmetro)
            estimated_time = len(candidate["path"]) * 3  # Placeholder simples
            
            # ✅ MELHOR: Calcular REAL considerando largura de banda
            min_bandwidth = float('inf')
            total_delay = 0
            
            path = candidate["path"]
            for i in range(len(path) - 1):
                link_data = self.server.model.topology[path[i]][path[i + 1]]
                link_bandwidth = link_data.get('bandwidth', 100)  # Mbps
                link_delay = link_data.get('delay', 0)
                
                min_bandwidth = min(min_bandwidth, link_bandwidth)
                total_delay += link_delay
            
            # Ajustar por downloads ativos no servidor fonte
            source_server = candidate["server"]
            active_downloads = len([
                flow for flow in source_server.download_queue 
                if hasattr(flow, 'source') and flow.source == source_server
            ]) if hasattr(source_server, 'download_queue') else 0
            
            effective_bandwidth = min_bandwidth / max(1, active_downloads)
            
            # Tempo estimado (simplificado: assumir camada média de 50MB)
            avg_layer_size_mb = 50
            bandwidth_mb_per_sec = effective_bandwidth / 8.0
            download_time = (avg_layer_size_mb / bandwidth_mb_per_sec) if bandwidth_mb_per_sec > 0 else float('inf')
            
            total_time = download_time + total_delay
            
            candidate["estimated_download_time"] = total_time
        
        # Ordenar por tempo estimado (menor primeiro)
        candidates_with_path.sort(key=lambda r: r["estimated_download_time"])
        
        best = candidates_with_path[0]
        
        # ✅ DEBUG (opcional)
        if len(candidates_with_path) > 1:
            print(f"[LAYER_SOURCE] Melhor fonte: {best['server'].id} (tempo estimado: {best['estimated_download_time']:.1f}s)")
            print(f"               Alternativas descartadas: {len(candidates_with_path)-1}")
        
        return best
    
    def create_download_flow(self, layer, source_server, path):
        """Cria o fluxo de download da camada."""
        flow = NetworkFlow(
            topology=self.server.model.topology,
            source=source_server,
            target=self.server,
            start=self.server.model.schedule.steps + 1,
            path=path,
            data_to_transfer=layer.size,
            metadata={"type": "layer", "object": layer, "source_server": source_server},
        )
        self.server.model.initialize_agent(agent=flow)
        return flow
    
    def process_next_layer(self):
        """Processa a próxima camada da fila de espera."""
        layer = self.server.waiting_queue.pop(0)
        
        # Encontrar fontes (respeitando configuração)
        sources = self.find_layer_sources(layer)
        candidates_with_path = self.calculate_paths_to_sources(sources)
        
        if not candidates_with_path:
            # ✅ Mensagem de debug mais informativa
            strategy_info = []
            if not self.config["enable_registry"]:
                strategy_info.append("Registries disabled")
            if not self.config["enable_p2p"]:
                strategy_info.append("P2P disabled")
            
            strategy_str = f" ({', '.join(strategy_info)})" if strategy_info else ""
            print(f"[EDGE_SERVER] ⚠️ Layer {layer.digest[:8]} not found in any available server{strategy_str}.")
            return False
        
        # Selecionar melhor fonte
        best_candidate = self.select_best_source(candidates_with_path)
        
        # Criar fluxo de download
        flow = self.create_download_flow(
            layer=layer,
            source_server=best_candidate["server"],
            path=best_candidate["path"]
        )
        
        # Adicionar à fila de downloads
        self.server.download_queue.append(flow)
        return True


# ═══════════════════════════════════════════════════════════════
# ✅ FUNÇÃO PRINCIPAL PARAMETRIZÁVEL
# ═══════════════════════════════════════════════════════════════

def edge_server_step(self, steps_to_execute=None):
    """
    Executa eventos do servidor de forma parametrizável.
    
    Args:
        steps_to_execute: Lista de etapas a executar. Se None, executa todas.
                         Opções: ['failure_management', 'interruptions', 'layer_provisioning']
    """
    # Configuração padrão: executar todas as etapas
    if steps_to_execute is None:
        steps_to_execute = ['failure_management', 'interruptions', 'layer_provisioning']
    
    # ═══════════════════════════════════════════════════════════════
    # ETAPA 1: GERENCIAMENTO DE FALHAS
    # ═══════════════════════════════════════════════════════════════
    if 'failure_management' in steps_to_execute:
        server_do_fail = (
            self.failure_model.failure_characteristics["number_of_failures"]["upper_bound"] > 0 and 
            self.failure_model.initial_failure_time_step != float("inf")
        )
        
        if server_do_fail:
            failure_executor = FailureManagementExecutor(self)
            
            # Gerar novo conjunto de falhas se necessário
            if failure_executor.should_generate_new_failure_set():
                failure_executor.generate_failure_set()
            
            # Obter falha em curso
            ongoing_failure = failure_executor.get_ongoing_failure()
            
            # Atualizar status do servidor
            failure_executor.update_server_status(ongoing_failure)
            
            # Atualizar disponibilidade dos serviços
            failure_executor.update_services_availability()
    
    # ═══════════════════════════════════════════════════════════════
    # ETAPA 2: INTERRUPÇÕES (quando servidor indisponível)
    # ═══════════════════════════════════════════════════════════════
    if 'interruptions' in steps_to_execute and not self.available:
        interruption_executor = FailureInterruptionExecutor(self)
        
        interruption_executor.clear_waiting_queue()
        interruption_executor.interrupt_downloads()
        interruption_executor.mark_migrations_for_cancellation()
        interruption_executor.reset_resource_demands()
    
    # ═══════════════════════════════════════════════════════════════
    # ETAPA 3: PROVISIONAMENTO DE CAMADAS
    # ═══════════════════════════════════════════════════════════════
    if 'layer_provisioning' in steps_to_execute:
        provisioning_executor = LayerProvisioningExecutor(self)
        
        while provisioning_executor.can_start_new_download():
            provisioning_executor.process_next_layer()


# ═══════════════════════════════════════════════════════════════
# ✅ PROPERTIES (mantidas inalteradas)
# ═══════════════════════════════════════════════════════════════

@property
def failure_history(self):
    """Provides compatibility with legacy code that accesses server.failure_history directly."""
    return self.failure_model.failure_history if hasattr(self, 'failure_model') else []


@property
def available_history(self):
    """Calculates and returns the server's availability history."""
    history = []
    
    if not hasattr(self, 'failure_model') or not self.failure_model.failure_trace:
        return history
    
    # Flatten failure trace
    all_failures = [failure for group in self.failure_model.failure_trace for failure in group]
    
    # Sort failures by start time
    all_failures.sort(key=lambda f: f["failure_starts_at"])
    
    current_time = self.failure_model.initial_failure_time_step
    
    for failure in all_failures:
        # Available period before failure
        if current_time < failure["failure_starts_at"]:
            history.append({
                "start": current_time,
                "end": failure["failure_starts_at"] - 1,
                "status": "available"
            })
        
        # Failure period
        history.append({
            "start": failure["failure_starts_at"],
            "end": failure["failure_ends_at"],
            "status": "failing"
        })
        
        # Booting period
        history.append({
            "start": failure["starts_booting_at"],
            "end": failure["finishes_booting_at"],
            "status": "booting"
        })
        
        current_time = failure["becomes_available_at"]
    
    return history