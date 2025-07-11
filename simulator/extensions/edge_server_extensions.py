"""This module contains the edge server extensions."""

# Importing EdgeSimPy components
from edge_sim_py.components.container_registry import ContainerRegistry
from edge_sim_py.components.network_flow import NetworkFlow
from edge_sim_py.components.service import Service

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
        # print(f"\n\n\n[STEP {self.model.schedule.steps}] {metadata}")

        if no_failure_has_occurred or last_failure_that_occurred_is_the_last_planned:
            interval_between_sets = randint(
                a=self.failure_model.failure_characteristics["interval_between_sets"]["lower_bound"],
                b=self.failure_model.failure_characteristics["interval_between_sets"]["upper_bound"],
            )
            next_failure_time_step = self.failure_model.failure_trace[-1][-1]["becomes_available_at"] + interval_between_sets

            # print(f"[STEP {self.model.schedule.steps}] Generating failure set for {self} with next_failure_time_step: {next_failure_time_step}")
            self.failure_model.generate_failure_set(next_failure_time_step=next_failure_time_step)

        # Filtering the failure history to get the ongoing failure (if any)
        flatten_failure_trace = [item for failure_group in self.failure_model.failure_trace for item in failure_group]
        ongoing_failure = next(
            (
                failure
                for failure in flatten_failure_trace
                if failure["failure_starts_at"] <= current_step + 1 and current_step <= failure["becomes_available_at"]
            ),
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

        if self.status == "available":
            for service in self.services:
                service._available = True

        # Interrupting any ongoing service provisioning processes attached to the server if it is not available
        else:
            # Emptying the server's waiting queue
            self.waiting_queue = []

            # Interrupting all network flows within the server's download queue
            for flow in self.download_queue:
                flow.data_to_transfer = 0
                flow.status = "interrupted"

            for service in Service.all():
                if service.server == self:
                    service._available = False

                service_has_migrations = len(service._Service__migrations) > 0
                if service_has_migrations:
                    migration = service._Service__migrations[-1]
                    if migration["origin"] == self or migration["target"] == self:
                        # Interrupting the ongoing service migration
                        migration["status"] = "interrupted"
                        migration["end"] = current_step + 1

                        # Updating the service's origin and target servers metadata
                        migration["target"].ongoing_migrations -= 1
                        if service.server:
                            service.server.ongoing_migrations -= 1

                        # Updating the service's availability status if it was being hosted by the server
                        service.being_provisioned = False
                        if service.server == self:
                            service._available = False

                            # Changing the routes used to communicate the application that owns the service to its users
                            app = service.application
                            users = app.users
                            for user in users:
                                user.set_communication_path(app)

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


@property
def failure_history(self):
    return [
        failure_occurrence
        for failure_occurrence in self.failure_model.failure_history
        if failure_occurrence["becomes_available_at"] < self.model.schedule.steps + 1
    ]
