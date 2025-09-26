"""This file contains a set of helper functions that facilitate the simulation execution."""

# Importing Python libraries
from random import choice, shuffle, sample
import matplotlib.pyplot as plt
import networkx as nx
from json import dumps
from random import sample, randint
import math  # Adicionado para cálculos matemáticos mais precisos

# Importing EdgeSimPy components
from edge_sim_py import *

# Importing EdgeSimPy extensions
from simulator.extensions import *

#from simulator.algorithms.trust_edge_v2 import get_user_perceived_downtime


def display_topology(topology: object, output_filename: str = "topology"):
    """Prints the network topology to an output file.

    Args:
        topology (object): Topology object.
        output_filename (str, optional): Output file name. Defaults to "topology".
    """
    # Customizing visual representation of topology
    positions = {}
    labels = {}
    colors = []
    sizes = []

    for node in topology.nodes():
        positions[node] = node.coordinates
        labels[node] = node.id
        node_size = 500 if any(user.coordinates == node.coordinates for user in User.all()) else 100
        sizes.append(node_size)

        if len(node.base_station.edge_servers) and sum(len(s.container_registries) for s in node.base_station.edge_servers) == 0:
            node_server = node.base_station.edge_servers[0]
            if node_server.model_name == "PowerEdge R620":
                colors.append("green")
            elif node_server.model_name == "SGI":
                colors.append("red")

        elif len(node.base_station.edge_servers) and sum(len(s.container_registries) for s in node.base_station.edge_servers) > 0:
            colors.append("blue")
        else:
            colors.append("black")

    # Configuring drawing scheme
    nx.draw(
        topology,
        pos=positions,
        node_color=colors,
        node_size=sizes,
        labels=labels,
        font_size=6,
        font_weight="bold",
        font_color="whitesmoke",
    )

    # Saving a topology image in the disk
    plt.savefig(f"{output_filename}.png", dpi=120)


def uniform(n_items: int, valid_values: list, shuffle_distribution: bool = True) -> list:
    """Creates a list of size "n_items" with values from "valid_values" according to the uniform distribution.
    By default, the method shuffles the created list to avoid unbalanced spread of the distribution.

    Args:
        n_items (int): Number of items that will be created.
        valid_values (list): List of valid values for the list of values.
        shuffle_distribution (bool, optional): Defines whether the distribution is shuffled or not. Defaults to True.

    Raises:
        Exception: Invalid "valid_values" argument.

    Returns:
        uniform_distribution (list): List of values arranged according to the uniform distribution.
    """
    if not isinstance(valid_values, list) or isinstance(valid_values, list) and len(valid_values) == 0:
        raise Exception("You must inform a list of valid values within the 'valid_values' attribute.")

    # Number of occurrences that will be created of each item in the "valid_values" list
    distribution = [int(n_items / len(valid_values)) for _ in range(0, len(valid_values))]

    # List with size "n_items" that will be populated with "valid_values" according to the uniform distribution
    uniform_distribution = []

    for i, value in enumerate(valid_values):
        for _ in range(0, int(distribution[i])):
            uniform_distribution.append(value)

    # Computing leftover randomly to avoid disturbing the distribution
    leftover = n_items % len(valid_values)
    for i in range(leftover):
        random_valid_value = choice(valid_values)
        uniform_distribution.append(random_valid_value)

    # Shuffling distribution values in case 'shuffle_distribution' parameter is True
    if shuffle_distribution:
        shuffle(uniform_distribution)

    return uniform_distribution


def min_max_norm(x, minimum, maximum):
    """Normalizes a given value (x) using the Min-Max Normalization method.

    Args:
        x (any): Value that must be normalized.
        min (any): Minimum value known.
        max (any): Maximum value known.

    Returns:
        (any): Normalized value.
    """
    if minimum == maximum:
        return 1
    return (x - minimum) / (maximum - minimum)


def find_minimum_and_maximum(metadata: list):
    """Finds the minimum and maximum values of a list of dictionaries.

    Args:
        metadata (list): List of dictionaries that contains the analyzed metadata.

    Returns:
        min_and_max (dict): Dictionary that contains the minimum and maximum values of the attributes.
    """
    min_and_max = {
        "minimum": {},
        "maximum": {},
    }

    for metadata_item in metadata:
        for attr_name, attr_value in metadata_item.items():
            if attr_name != "object" and type(attr_value) != list:
                # Updating the attribute's minimum value
                if attr_name not in min_and_max["minimum"] or attr_name in min_and_max["minimum"] and attr_value < min_and_max["minimum"][attr_name]:
                    min_and_max["minimum"][attr_name] = attr_value

                # Updating the attribute's maximum value
                if attr_name not in min_and_max["maximum"] or attr_name in min_and_max["maximum"] and attr_value > min_and_max["maximum"][attr_name]:
                    min_and_max["maximum"][attr_name] = attr_value

    return min_and_max


def get_norm(metadata: dict, attr_name: str, min: dict, max: dict) -> float:
    """Wrapper to normalize a value using the Min-Max Normalization method.

    Args:
        metadata (dict): Dictionary that contains the metadata of the object whose values are being normalized.
        attr_name (str): Name of the attribute that must be normalized.
        min (dict): Dictionary that contains the minimum values of the attributes.
        max (dict): Dictionary that contains the maximum values of the attributes.

    Returns:
        normalized_value (float): Normalized value.
    """
    normalized_value = min_max_norm(x=metadata[attr_name], minimum=min[attr_name], maximum=max[attr_name])
    return normalized_value


def normalize_cpu_and_memory(cpu, memory) -> float:
    """Normalizes the CPU and memory values.

    Args:
        cpu (float): CPU value.
        memory (float): Memory value.

    Returns:
        normalized_value (float): Normalized value.
    """
    normalized_value = (cpu * memory) ** (1 / 2)
    return normalized_value


def get_normalized_capacity(object: object) -> float:
    """Returns the normalized capacity of a given entity.

    Args:
        object (object): Entity object to be analyzed.

    Returns:
        (float): Normalized capacity of the given entity.
    """
    return (object.cpu * object.memory * object.disk) ** (1 / 3)


def get_normalized_free_capacity(object: object) -> float:
    """Returns the normalized free capacity of a given entity.

    Args:
        object (object): Entity object to be analyzed.

    Returns:
        (float): Normalized capacity of the given entity.
    """
    free_cpu = object.cpu - object.cpu_demand
    free_memory = object.memory - object.memory_demand
    free_disk = object.disk - object.disk_demand
    
    # Retorna 0 se qualquer uma das capacidades livres for zero ou negativa
    if free_cpu <= 0 or free_memory <= 0 or free_disk <= 0:
        return 0.0
   
    return (free_cpu * free_memory * free_disk) ** (1 / 3)


def get_normalized_demand(object: object) -> float:
    """Returns the normalized demand of a given entity.

    Args:
        object (object): Entity object to be analyzed.

    Returns:
        (float): Normalized demand of the given entity.
    """
    if hasattr(object, "disk_demand"):
        return (object.cpu_demand * object.memory_demand * object.disk_demand) ** (1 / 3)
    else:
        return (object.cpu_demand * object.memory_demand) ** (1 / 2)


def get_shortest_path(origin_switch: object, target_switch: object) -> list:
    """Gets the shortest path between two network nodes (i.e., network switches).

    Args:
        origin_switch (object): Origin network switch.
        target_switch (object): Target network switch.

    Returns:
        shortest_path (list): Shortest network path found.
    """
    topology = origin_switch.model.topology

    if not hasattr(topology, "shortest_paths"):
        topology.shortest_paths = {}

    if frozenset([origin_switch.id, target_switch.id]) in topology.shortest_paths:
        return topology.shortest_paths[frozenset([origin_switch.id, target_switch.id])]
    else:
        shortest_path = nx.shortest_path(
            G=topology,
            source=origin_switch,
            target=target_switch,
            weight="delay",
        )
        topology.shortest_paths[frozenset([origin_switch.id, target_switch.id])] = shortest_path
        return topology.shortest_paths[frozenset([origin_switch.id, target_switch.id])]


def get_delay(wireless_delay: int, origin_switch: object, target_switch: object) -> int:
    """Gets the distance (in terms of delay) between two elements (origin and target).

    Args:
        wireless_delay (int): Wireless delay that must be included in the delay calculation.
        origin_switch (object): Origin switch.
        target_switch (object): Target switch.

    Returns:
        delay (int): Delay between the origin and target switches.
    """
    topology = origin_switch.model.topology

    path = get_shortest_path(origin_switch=origin_switch, target_switch=target_switch)
    delay = wireless_delay + topology.calculate_path_delay(path=path)

    return delay


def randomized_closest_fit():
    """Encapsulates a randomized closest-fit service placement algorithm."""
    services = sample(Service.all(), Service.count())
    for service in services:
        app = service.application
        user = app.users[0]
        user_switch = user.base_station.network_switch

        edge_servers = []
        for edge_server in sample(EdgeServer.all(), EdgeServer.count()):
            path = nx.shortest_path(
                G=Topology.first(),
                source=user_switch,
                target=edge_server.network_switch,
                weight="delay",
            )
            delay = Topology.first().calculate_path_delay(path=path)
            edge_servers.append(
                {
                    "object": edge_server,
                    "path": path,
                    "delay": delay,
                    "violates_sla": delay > user.delay_slas[str(service.application.id)],
                    "free_capacity": get_normalized_capacity(object=edge_server) - get_normalized_demand(object=edge_server),
                }
            )

        edge_servers = sorted(edge_servers, key=lambda s: (s["violates_sla"], randint(0, 100)))

        for edge_server_metadata in edge_servers:
            edge_server = edge_server_metadata["object"]

            # Checking if the host would have resources to host the service and its (additional) layers
            if edge_server.has_capacity_to_host(service=service):
                # Updating the host's resource usage
                edge_server.cpu_demand += service.cpu_demand
                edge_server.memory_demand += service.memory_demand

                # Creating relationship between the host and the registry
                service.server = edge_server
                edge_server.services.append(service)

                for layer_metadata in edge_server._get_uncached_layers(service=service):
                    layer = ContainerLayer(
                        digest=layer_metadata.digest,
                        size=layer_metadata.size,
                        instruction=layer_metadata.instruction,
                    )

                    # Updating host's resource usage based on the layer size
                    edge_server.disk_demand += layer.size

                    # Creating relationship between the host and the layer
                    layer.server = edge_server
                    edge_server.container_layers.append(layer)

                break

        # Creating an instance of the service image on its host if necessary
        if not any(hosted_image for hosted_image in service.server.container_images if hosted_image.digest == service.image_digest):
            template_image = next(
                (img for img in ContainerImage.all() if img.digest == service.image_digest),
                None,
            )

            # Creating a ContainerImage object to represent the new image
            image = ContainerImage()
            image.name = template_image.name
            image.digest = template_image.digest
            image.tag = template_image.tag
            image.layers_digests = template_image.layers_digests

            # Connecting the new image to the target host
            image.server = service.server
            service.server.container_images.append(image)


def show_scenario_overview():
    print("\n\n")
    print("======================")
    print("==== EDGE SERVERS ====")
    print("======================")
    for edge_server in EdgeServer.all():
        edge_server_metadata = {
            "base_station": edge_server.base_station,
            "capacity": [edge_server.cpu, edge_server.memory, edge_server.disk],
            "demand": [edge_server.cpu_demand, edge_server.memory_demand, edge_server.disk_demand],
            "services": [service.id for service in edge_server.services],
            "layers": [layer.id for layer in edge_server.container_layers],
            "images": [image.id for image in edge_server.container_images],
        }
        print(f"{edge_server}. {edge_server_metadata}")

    print("\n\n")
    print("======================")
    print("==== APPLICATIONS ====")
    print("======================")
    print(f"Number of Applications/Services/Users: {Application.count()}/{Service.count()}/{User.count()}")
    for application in Application.all():
        user = application.users[0]
        service = application.services[0]
        image = ContainerImage.find_by(attribute_name="digest", attribute_value=service.image_digest)
        application_metadata = {
            "delay_sla": user.delay_slas[str(application.id)],
            "delay": user.delays[str(application.id)],
            "image": image.name,
            "state": service.state,
            "demand": [service.cpu_demand, service.memory_demand],
            "host": f"{service.server}. Model: {service.server.model_name} ({service.server.status})",
        }
        print(f"\t{application}. {application_metadata}")

    print("\n\n")
    print("==========================")
    print("==== CONTAINER ASSETS ====")
    print("==========================")
    print(f"==== CONTAINER IMAGES ({ContainerImage.count()}):")
    for container_image in ContainerImage.all():
        print(f"\t{container_image}. Server: {container_image.server}")

    print("")

    print(f"==== CONTAINER LAYERS ({ContainerLayer.count()}):")
    for container_layer in ContainerLayer.all():
        print(f"\t{container_layer}. Server: {container_layer.server}")
    ##########################
    #### DATASET ANALYSIS ####
    ##########################
    # Calculating the network delay between users and edge servers (useful for defining reasonable delay SLAs)
    users = []
    for user in User.all():
        user_metadata = {
            "object": user,
            "sla": user.delay_slas[str(user.applications[0].id)],
            "all_delays": [],
            "hosts_that_meet_the_sla": [],
        }
        edge_servers = []
        for edge_server in EdgeServer.all():
            path = nx.shortest_path(G=Topology.first(), source=user.base_station.network_switch, target=edge_server.network_switch, weight="delay")
            path_delay = Topology.first().calculate_path_delay(path=path)
            user_metadata["all_delays"].append(path_delay)
            if user_metadata["sla"] >= path_delay:
                user_metadata["hosts_that_meet_the_sla"].append(edge_server)

        user_metadata["min_delay"] = min(user_metadata["all_delays"])
        user_metadata["max_delay"] = max(user_metadata["all_delays"])
        user_metadata["avg_delay"] = sum(user_metadata["all_delays"]) / len(user_metadata["all_delays"])
        user_metadata["delays"] = {}
        for delay in sorted(list(set(user_metadata["all_delays"]))):
            user_metadata["delays"][delay] = user_metadata["all_delays"].count(delay)

        users.append(user_metadata)

    print("\n\n")
    print("=================================================================")
    print("==== NETWORK DISTANCE (DELAY) BETWEEN USERS AND EDGE SERVERS ====")
    print("=================================================================")
    users = sorted(users, key=lambda user_metadata: (user_metadata["sla"], len(user_metadata["hosts_that_meet_the_sla"])))
    for index, user_metadata in enumerate(users, 1):
        user_attrs = {
            "object": user_metadata["object"],
            "sla": user_metadata["object"].delay_slas[str(user_metadata["object"].applications[0].id)],
            "hosts_that_meet_the_sla": len(user_metadata["hosts_that_meet_the_sla"]),
            "min": user_metadata["min_delay"],
            "max": user_metadata["max_delay"],
            "avg": round(user_metadata["avg_delay"]),
            "delays": user_metadata["delays"],
        }
        print(f"[{index}] {user_attrs}")
        if user_attrs["min"] > user_attrs["sla"]:
            print(f"\n\n\n\nWARNING: {user_attrs['object']} delay SLA is not achievable!\n\n\n\n")
        if user_attrs["max"] <= user_attrs["sla"]:
            print(f"\n\n\n\nWARNING: {user_attrs['object']} delay SLA is achievable by any edge server!\n\n\n\n")

    # Calculating the infrastructure occupation and information about the services
    edge_server_cpu_capacity = 0
    edge_server_memory_capacity = 0
    service_cpu_demand = 0
    service_memory_demand = 0

    for edge_server in EdgeServer.all():
        if len(edge_server.container_registries) == 0:
            edge_server_cpu_capacity += edge_server.cpu
            edge_server_memory_capacity += edge_server.memory

    for service in Service.all():
        service_cpu_demand += service.cpu_demand
        service_memory_demand += service.memory_demand

    overall_cpu_occupation = round((service_cpu_demand / edge_server_cpu_capacity) * 100, 1)
    overall_memory_occupation = round((service_memory_demand / edge_server_memory_capacity) * 100, 1)

    print("\n\n")
    print("============================================")
    print("============================================")
    print("==== INFRASTRUCTURE OCCUPATION OVERVIEW ====")
    print("============================================")
    print("============================================")
    print(f"Edge Servers: {EdgeServer.count()}")
    print(f"\tCPU Capacity: {edge_server_cpu_capacity}")
    print(f"\tRAM Capacity: {edge_server_memory_capacity}")

    print("")

    print(f"Idle Edge Servers: {sum([1 for s in EdgeServer.all() if s.cpu_demand == 0])}")

    print("")

    print(f"Services: {Service.count()}")
    print(f"\tCPU Demand: {service_cpu_demand}")

    print(f"\nOverall Occupation")
    print(f"\tCPU: {overall_cpu_occupation}%")
    print(f"\tRAM: {overall_memory_occupation}%")


def find_shortest_path(origin_network_switch: object, target_network_switch: object) -> int:
    """Finds the shortest path (delay used as weight) between two network switches (origin and target).

    Args:
        origin_network_switch (object): Origin network switch.
        target_network_switch (object): Target network switch.

    Returns:
        path (list): Shortest path between the origin and target network switches.
    """
    topology = origin_network_switch.model.topology
    path = []

    if not hasattr(topology, "delay_shortest_paths"):
        topology.delay_shortest_paths = {}

    key = (origin_network_switch, target_network_switch)

    if key in topology.delay_shortest_paths.keys():
        path = topology.delay_shortest_paths[key]
    else:
        path = nx.shortest_path(G=topology, source=origin_network_switch, target=target_network_switch, weight="delay")
        topology.delay_shortest_paths[key] = path

    return path


def calculate_path_delay(origin_network_switch: object, target_network_switch: object) -> int:
    """Gets the distance (in terms of delay) between two network switches (origin and target).

    Args:
        origin_network_switch (object): Origin network switch.
        target_network_switch (object): Target network switch.

    Returns:
        delay (int): Delay between the origin and target network switches.
    """
    topology = origin_network_switch.model.topology

    path = find_shortest_path(origin_network_switch=origin_network_switch, target_network_switch=target_network_switch)
    delay = topology.calculate_path_delay(path=path)

    return delay


def sign(value: int):
    """Calculates the sign of a real number using the well-known "sign" function (https://wikipedia.org/wiki/Sign_function).

    Args:
        value (int): Value whose sign must be calculated.

    Returns:
        (int): Sign of the passed value.
    """
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def provision(user: object, application: object, service: object, edge_server: object):
    """Provisions an application's service on an edge server.

    Args:
        user (object): User that accesses the application.
        application (object): Application to whom the service belongs.
        service (object): Service to be provisioned.
        edge_server (object): Edge server that will host the edge server.
    """
    # Updating the host's resource usage
    edge_server.cpu_demand += service.cpu_demand
    edge_server.memory_demand += service.memory_demand

    # Creating relationship between the host and the registry
    service.server = edge_server
    edge_server.services.append(service)

    for layer_metadata in edge_server._get_uncached_layers(service=service):
        layer = ContainerLayer(
            digest=layer_metadata.digest,
            size=layer_metadata.size,
            instruction=layer_metadata.instruction,
        )

        # Updating host's resource usage based on the layer size
        edge_server.disk_demand += layer.size

        # Creating relationship between the host and the layer
        layer.server = edge_server
        edge_server.container_layers.append(layer)

    user.set_communication_path(app=application)

    
def reset_server(edge_server: object):
    # Resets the edge server's resource demands.

    # Resetting the demand
    edge_server.cpu_demand = 0
    edge_server.memory_demand = 0
    edge_server.disk_demand = 0

    # Deprovisioning services
    for service in edge_server.services:
        service.server = None
    edge_server.services = []

    # Removing layers from edge servers not initially set as hosts for container registries
    if len(edge_server.container_registries) == 0:
        layers = list(edge_server.container_layers)
        edge_server.container_layers = []
        for layer in layers:
            layer.server = None
            ContainerLayer.remove(layer)

    for user in User.all():
        for app in user.applications:
            user.delays[str(app.id)] = 0
            user.communication_paths[str(app.id)] = []


def user_set_communication_path(self, app: object, communication_path: list = []) -> list:
    """Updates the set of links used during the communication of user and its application.

    Args:
        app (object): User application.
        communication_path (list, optional): User-specified communication path. Defaults to [].

    Returns:
        communication_path (list): Updated communication path.
    """
    topology = Topology.first()

    # Releasing links used in the past to connect the user with its application
    if app in self.communication_paths:
        path = [[NetworkSwitch.find_by_id(i) for i in p] for p in self.communication_paths[str(app.id)]]
        topology._release_communication_path(communication_path=path, app=app)

    # Defining communication path
    if len(communication_path) > 0:
        self.communication_paths[str(app.id)] = communication_path
    else:
        self.communication_paths[str(app.id)] = []

        service_hosts_base_stations = [service.server.base_station for service in app.services if service.server]
        communication_chain = [self.base_station] + service_hosts_base_stations

        # Defining a set of links to connect the items in the application's service chain
        for i in range(len(communication_chain) - 1):

            # Defining origin and target nodes
            origin = communication_chain[i]
            target = communication_chain[i + 1]

            # Finding and storing the best communication path between the origin and target nodes
            if origin == target:
                path = []
            else:
                path = find_shortest_path(origin_network_switch=origin.network_switch, target_network_switch=target.network_switch)

            # Adding the best path found to the communication path
            self.communication_paths[str(app.id)].append([network_switch.id for network_switch in path])

            # Computing the new demand of chosen links
            path = [[NetworkSwitch.find_by_id(i) for i in p] for p in self.communication_paths[str(app.id)]]
            topology._allocate_communication_path(communication_path=path, app=app)

    # Computing application's delay
    self._compute_delay(app=app, metric="latency")

    communication_path = self.communication_paths[str(app.id)]
    return communication_path


def topology_collect(self) -> dict:
    """Method that collects a set of metrics for the object.

    The network topology aggregates the following metrics from the simulation:
        1. Infrastructure Usage
            - Overall Occupation
            - Occupation per Infrastructure Provider
            - Occupation per Server Model
            - Active Servers per Infrastructure Provider
            - Active Servers per Model
            - Power Consumption
                - Overall Power Consumption
                - Power Consumption per Server Model
        2. SLA Violations
            - Number of Delay SLA Violations
            - Number of Privacy SLA Violations
            - Number of Delay SLA Violations per Application Chain Size
            - Privacy Violations per Application Delay SLA
            - Privacy Violations per Service Privacy Requirement

    Returns:
        metrics (dict): Object metrics.
    """
    # Declaring infrastructure metrics
    overloaded_edge_servers = 0
    overall_occupation = 0
    occupation_per_model = {}
    overall_power_consumption = 0
    power_consumption_per_server_model = {}
    active_servers_per_model = {}

    # Declaring delay SLA metrics
    delay_sla_violations = 0
    delay_violations_per_delay_sla = {}
    

    # Declaring availability metrics
    user_total_perceived_downtime = 0
    total_perceived_downtime_per_access_pattern = {}
    delay_violations_per_access_pattern = {}

    # Collecting infrastructure metrics
    for edge_server in EdgeServer.all():
        # Overall Occupation
        capacity = normalize_cpu_and_memory(cpu=edge_server.cpu, memory=edge_server.memory)
        demand = normalize_cpu_and_memory(cpu=edge_server.cpu_demand, memory=edge_server.memory_demand)
        overall_occupation += demand / capacity * 100
        overall_power_consumption += edge_server.get_power_consumption()

        # Number of overloaded edge servers
        free_cpu = edge_server.cpu - edge_server.cpu_demand
        free_memory = edge_server.memory - edge_server.memory_demand
        free_disk = edge_server.disk - edge_server.disk_demand
        if free_cpu < 0 or free_memory < 0 or free_disk < 0:
            overloaded_edge_servers += 1

        # Occupation per Server Model
        if edge_server.model_name not in occupation_per_model.keys():
            occupation_per_model[edge_server.model_name] = []
        occupation_per_model[edge_server.model_name].append(demand / capacity * 100)

        # Power consumption per Server Model
        if edge_server.model_name not in power_consumption_per_server_model.keys():
            power_consumption_per_server_model[edge_server.model_name] = []
        power_consumption_per_server_model[edge_server.model_name].append(edge_server.get_power_consumption())

    # Aggregating overall metrics
    overall_occupation = overall_occupation / EdgeServer.count()

    for model_name in occupation_per_model.keys():
        active_servers_per_model[model_name] = len([item for item in occupation_per_model[model_name] if item > 0])
        occupation_per_model[model_name] = sum(occupation_per_model[model_name]) / len(occupation_per_model[model_name])

    # Collecting delay SLA metrics
    for user in User.all():
        for app in user.applications:
            user.set_communication_path(app=app)
            delay_sla = user.delay_slas[str(app.id)]
            delay = user._compute_delay(app=app, metric="latency")

            access_pattern = user.access_patterns[str(app.id)]
            duration = access_pattern.duration_values[0]
            
            # Calculating the number of delay SLA violations
            if delay > delay_sla:
                delay_sla_violations += 1

                if delay_sla not in delay_violations_per_delay_sla.keys():
                    delay_violations_per_delay_sla[delay_sla] = 0
                delay_violations_per_delay_sla[delay_sla] += 1

                if duration not in delay_violations_per_access_pattern.keys():
                    delay_violations_per_access_pattern[duration] = 0
                delay_violations_per_access_pattern[duration] += 1

    data = {}
    data["model"] = []
    for model_name in set([server.model_name for server in EdgeServer.all()]):
        data["model"].append(
            {
                "model_name": model_name,
                "occupation": occupation_per_model[model_name],
                "power_consumption": sum(power_consumption_per_server_model[model_name]),
                "active_servers": active_servers_per_model[model_name],
            }
        )

    data["delay_sla"] = []
    for delay_sla in set([user.delay_slas[str(app.id)] for user in User.all() for app in user.applications]):
        data["delay_sla"].append(
            {
                "delay_sla": delay_sla,
                "delay_sla_violations": delay_violations_per_delay_sla.get(delay_sla, None),
            }
        )
    # Collecting availability metrics
    for user in User.all():
        for app in user.applications:
            perceived_downtime = sum(1 for status in app.downtime_history if status)
            user_total_perceived_downtime += perceived_downtime

            access_pattern = user.access_patterns[str(app.id)]
            duration = access_pattern.duration_values[0]

            if duration not in total_perceived_downtime_per_access_pattern.keys():
                total_perceived_downtime_per_access_pattern[duration] = 0
            total_perceived_downtime_per_access_pattern[duration] += perceived_downtime

    metrics = {
        "overloaded_edge_servers": overloaded_edge_servers,
        "overall_occupation": overall_occupation,
        "occupation_per_model": occupation_per_model,
        "overall_power_consumption": overall_power_consumption,
        "power_consumption_per_server_model": power_consumption_per_server_model,
        "active_servers_per_model": active_servers_per_model,
        "delay_violations_per_delay_sla": delay_violations_per_delay_sla,
        "delay_violations_per_access_pattern": delay_violations_per_access_pattern,
        "user_total_perceived_downtime": user_total_perceived_downtime,
        "total_perceived_downtime_per_access_pattern": total_perceived_downtime_per_access_pattern,
        "raw_data": data,
    }

    return metrics