"""This module contains the edge server extensions."""

# Importing EdgeSimPy components
from edge_sim_py.components.container_registry import ContainerRegistry
from edge_sim_py.components.network_flow import NetworkFlow
from edge_sim_py.components.service import Service
from edge_sim_py.components.edge_server import EdgeServer

# Importing Python modules
import networkx as nx
from random import randint


def edge_server_step(self):
    """Method that executes the events involving the object at each time step."""
    # Failure management
    current_step = self.model.schedule.steps + 1
    no_failure_has_occurred = len(self.failure_model.failure_history) == 0
    server_do_fail = self.failure_model.failure_characteristics["number_of_failures"]["upper_bound"] > 0 and self.failure_model.initial_failure_time_step != float("inf")

    if server_do_fail:
        if len(self.failure_model.failure_history) == 0:
            last_failure_that_occurred_is_the_last_planned = True
        else:
            last_failure_that_occurred_is_the_last_planned = self.failure_model.failure_history[-1] == self.failure_model.failure_trace[-1][-1]

        metadata = {
            "obj": self,
            "last_failure_that_occurred": self.failure_model.failure_trace[-1][-1],
            "failure_characteristics": self.failure_model.failure_characteristics,
            "no_failure_has_occurred": no_failure_has_occurred,
            "last_failure_that_occurred_is_the_last_planned": last_failure_that_occurred_is_the_last_planned,
        }

        if no_failure_has_occurred or last_failure_that_occurred_is_the_last_planned:
            interval_between_sets = randint(
                a=self.failure_model.failure_characteristics["interval_between_sets"]["lower_bound"],
                b=self.failure_model.failure_characteristics["interval_between_sets"]["upper_bound"],
            )
            next_failure_time_step = self.failure_model.failure_trace[-1][-1]["becomes_available_at"] + interval_between_sets
            self.failure_model.generate_failure_set(next_failure_time_step=next_failure_time_step)

        # Filtering the failure history to get the ongoing failure (if any)
        flatten_failure_trace = [item for failure_group in self.failure_model.failure_trace for item in failure_group]
        ongoing_failure = next(
            (
                failure
                for failure in flatten_failure_trace
                if failure["failure_starts_at"] <= current_step and current_step <= failure["becomes_available_at"]
            ),
            None,
        )
        
        # Updating the server status based on the ongoing failure status (if any)
        if ongoing_failure is not None:
            # Checking whether the server status should be changed from "available" to "failing"
            if self.status == "available" and current_step >= ongoing_failure["failure_starts_at"] and current_step < ongoing_failure["starts_booting_at"]:
                self.status = "failing"
                self.available = False

            # Checking whether the server status should be changed from "failing" to "booting"
            elif self.status == "failing" and current_step >= ongoing_failure["starts_booting_at"] and current_step < ongoing_failure["becomes_available_at"]:
                self.status = "booting"
                self.available = False

            # Checking whether the server status should be changed from "booting" to "available"
            elif self.status == "booting" and current_step >= ongoing_failure["becomes_available_at"]:
                self.status = "available"
                self.available = True
                if ongoing_failure not in self.failure_model.failure_history:
                    self.failure_model.failure_history.append(ongoing_failure)
        else:
            # If there is no ongoing failure, we can consider the server as healthy
            self.status = "available"
            self.available = True

        if self.status == "available":
            for service in self.services:
                if not service.being_provisioned:
                    service._available = True

        # Interrupting any ongoing service provisioning processes attached to the server if it is not available
        else:
            # Emptying the server's waiting queue
            self.waiting_queue = []

            # Interrupting all network flows within the server's download queue
            for flow in self.download_queue:
                flow.data_to_transfer = 0
                flow.status = "interrupted"
            
            # Limpar download_queue após interromper
            # self.download_queue = []

            # Marcar serviços deste servidor como indisponíveis
            for service in list(self.services):
                service._available = False

            # ✅ MARCAR MIGRAÇÕES PARA CANCELAMENTO (já existente)
            for service in Service.all():
                if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
                    continue
                
                migration = service._Service__migrations[-1]
                
                # Pular migrações já finalizadas
                if migration.get("end") is not None:
                    continue
                
                target = migration.get("target")
                
                # Se este servidor é DESTINO da migração → Marcar para cancelamento
                if target == self:
                    migration["_pending_cancellation"] = True
                    migration["_cancellation_reason"] = "target_server_failed"
                    print(f"[EDGE_SERVER] Migração do serviço {service.id} MARCADA para cancelamento (target falhou)")

            # ═══════════════════════════════════════════════════════════════
            # ✅ PASSO 3: ZERAR RECURSOS (DEPOIS DE LIMPAR ÓRFÃOS)
            # ═══════════════════════════════════════════════════════════════
            self.cpu_demand = 0
            self.memory_demand = 0

    # Container provisioning management
    while len(self.waiting_queue) > 0 and len(self.download_queue) < self.max_concurrent_layer_downloads:
        layer = self.waiting_queue.pop(0)

        # Gathering the list of sources (Registries and Edge Servers) that have the layer
        candidates = []

        # 1. Check Container Registries (Fonte Original)
        for registry in [reg for reg in ContainerRegistry.all() if reg.available]:
            if registry.server and any(layer.digest == l.digest for l in registry.server.container_layers):
                candidates.append(registry.server)

        # 2. Check other Edge Servers (Peer-to-Peer / Edge Caching)
        # Exclui o próprio servidor (self) e servidores indisponíveis
        for server in [s for s in EdgeServer.all() if s.available and s.id != self.id]:
            if any(layer.digest == l.digest for l in server.container_layers):
                candidates.append(server)

        # Calculating paths to candidates to find the closest one
        candidates_with_path = []
        for source_server in candidates:
            try:
                path = nx.shortest_path(
                    G=self.model.topology,
                    source=source_server.base_station.network_switch,
                    target=self.base_station.network_switch,
                )
                candidates_with_path.append({"server": source_server, "path": path})
            except nx.NetworkXNoPath:
                continue
        
        if not candidates_with_path:
            # Se a camada não for encontrada em lugar nenhum (erro crítico ou registry offline)
            print(f"[EDGE_SERVER] ⚠️ Layer {layer.digest[:8]} not found in any available server.")
            continue

        # Selecting the closest source (shortest path / fewer hops)
        # Isso satisfaz a condição: "o sentido mais próximo é o que levaria menos tempo"
        candidates_with_path.sort(key=lambda r: len(r["path"]))
        
        best_candidate = candidates_with_path[0]
        source_server = best_candidate["server"]
        path = best_candidate["path"]

        # Creating the flow object
        flow = NetworkFlow(
            topology=self.model.topology,
            source=source_server,
            target=self,
            start=self.model.schedule.steps + 1,
            path=path,
            data_to_transfer=layer.size,
            metadata={"type": "layer", "object": layer, "source_server": source_server},
        )
        self.model.initialize_agent(agent=flow)

        # Adding the created flow to the edge server's download queue
        self.download_queue.append(flow)


@property
def failure_history(self):
    return [
        failure_occurrence
        for failure_occurrence in self.failure_model.failure_history
        if failure_occurrence["becomes_available_at"] <= self.model.schedule.steps
    ]

@property
def available_history(self):
    """Returns the server's availability history."""
    if not hasattr(self, "_available_history"):
        self._available_history = []

    current_step = self.model.schedule.steps
    if len(self._available_history) <= current_step:
        self._available_history.append(self.available)

    return self._available_history