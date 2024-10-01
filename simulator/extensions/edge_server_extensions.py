from edge_sim_py.components.container_registry import ContainerRegistry
from edge_sim_py.components.network_flow import NetworkFlow
import networkx as nx
from random import randint


def edge_server_step(self):
    """Method that executes the events involving the object at each time step."""
    # Failure management
    current_step = self.model.schedule.steps + 1
    no_failure_has_ocurred = len(self.failure_model.failure_history) == 0
    if len(self.failure_model.failure_history) == 0:
        last_failure_that_ocurred_is_the_last_planned = True
    else:
        last_failure_that_ocurred_is_the_last_planned = self.failure_model.failure_history[-1] == self.failure_model.failure_trace[-1][-1]

    if no_failure_has_ocurred or last_failure_that_ocurred_is_the_last_planned:
        interval_between_sets = randint(
            a=self.failure_model.failure_characteristics["interval_between_sets"]["lower_bound"],
            b=self.failure_model.failure_characteristics["interval_between_sets"]["upper_bound"],
        )
        next_failure_time_step = self.failure_model.failure_trace[-1][-1]["becomes_available_at"] + interval_between_sets
        self.failure_model.generate_failure_set(next_failure_time_step=next_failure_time_step)

    # Filtering the failure history to get the ongoing failure (if any)
    flatten_failure_trace = [item for failure_group in self.failure_model.failure_trace for item in failure_group]
    ongoing_failure = next(
        (failure for failure in flatten_failure_trace if failure["failure_starts_at"] <= current_step + 1 and current_step <= failure["becomes_available_at"]),
        [],
    )

    # Updating the server status based on the ongoing failure status (if any)
    if len(ongoing_failure) > 0:
        # Checking whether the server status should be changed from "available" to "failing"
        if self.status == "available" and current_step + 1 == ongoing_failure["failure_starts_at"]:
            self.status = "failing"
            self.available = False

        # Checking whether the server status should be changed from "failing" to "booting"
        elif self.status == "failing" and current_step + 1 == ongoing_failure["starts_booting_at"]:
            self.status = "booting"

        # Checking whether the server status should be changed from "booting" to "available"
        elif self.status == "booting" and current_step + 1 == ongoing_failure["becomes_available_at"]:
            self.status = "available"
            self.available = True
            if ongoing_failure not in self.failure_model.failure_history:
                self.failure_model.failure_history.append(ongoing_failure)

    # Container provisioning management
    while len(self.waiting_queue) > 0 and len(self.download_queue) < self.max_concurrent_layer_downloads:
        layer = self.waiting_queue.pop(0)

        # Gathering the list of registries that have the layer
        registries_with_layer = []
        for registry in [reg for reg in ContainerRegistry.all() if reg.available]:
            # Checking if the registry is hosted on a valid host in the infrastructure and if it has the layer we need to pull
            if registry.server and any(layer.digest == l.digest for l in registry.server.container_layers):
                # Selecting a network path to be used to pull the layer from the registry
                path = nx.shortest_path(
                    G=self.model.topology,
                    source=registry.server.base_station.network_switch,
                    target=self.base_station.network_switch,
                )

                registries_with_layer.append({"object": registry, "path": path})

        # Selecting the registry from which the layer will be pulled to the (target) edge server
        registries_with_layer = sorted(registries_with_layer, key=lambda r: len(r["path"]))
        registry = registries_with_layer[0]["object"]
        path = registries_with_layer[0]["path"]

        # Creating the flow object
        flow = NetworkFlow(
            topology=self.model.topology,
            source=registry.server,
            target=self,
            start=self.model.schedule.steps + 1,
            path=path,
            data_to_transfer=layer.size,
            metadata={"type": "layer", "object": layer, "container_registry": registry},
        )
        self.model.initialize_agent(agent=flow)

        # Adding the created flow to the edge server's download queue
        self.download_queue.append(flow)
