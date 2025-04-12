"""This file contains a set of helper functions that facilitate the simulation execution."""

# Importing Python libraries
from random import choice, shuffle, sample
import matplotlib.pyplot as plt
import networkx as nx
from json import dumps
from random import sample, randint

# Importing EdgeSimPy components
from edge_sim_py import *


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


def get_normalized_capacity(object: object) -> float:
    """Returns the normalized capacity of a given entity.

    Args:
        object (object): Entity object to be analyzed.

    Returns:
        (float): Normalized capacity of the given entity.
    """
    return (object.cpu * object.memory * object.disk) ** (1 / 3)


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


def get_server_total_failures(server):
    history = server.failure_model.failure_history
    return len(history)


def get_server_mttr(server):
    history = server.failure_model.failure_history
    repair_times = []
    for failure_occurrence in history:
        repair_times.append(failure_occurrence["becomes_available_at"] - failure_occurrence["failure_starts_at"])

    return sum(repair_times) / len(repair_times) if repair_times else 0


def get_server_mtbf(server):
    number_of_failures = len(server.failure_model.failure_history)

    return get_server_uptime(server) / number_of_failures if number_of_failures > 0 else 0


def get_server_failure_rate(server):
    return 1 / get_server_mtbf(server) if get_server_mtbf(server) != 0 else float("inf")


def get_server_conditional_reliability(server, upcoming_instants):
    history = server.failure_model.failure_history
    server_failure_rate = get_server_failure_rate(server)
    return 2.71828 ** (-server_failure_rate * (len(history) + upcoming_instants)) / 2.71828 ** (-server_failure_rate * len(history))


def get_server_downtime(server):
    final_time_step = server.model.schedule.steps + 1
    total_downtime = 0
    for failure_occurrence in server.failure_model.failure_history:
        if failure_occurrence["failure_starts_at"] < final_time_step:
            total_downtime += failure_occurrence["becomes_available_at"] - failure_occurrence["failure_starts_at"]

    return total_downtime


def get_server_uptime(server):
    initial_time_step = server.failure_model.failure_history[0]["failure_starts_at"]
    final_time_step = server.model.schedule.steps + 1

    total_time_span = final_time_step - initial_time_step
    total_downtime = get_server_downtime(server=server)
    total_uptime = total_time_span - total_downtime

    return total_uptime


def get_application_downtime(application):
    downtime_count = 0
    for availability_status in application.availability_history:
        if availability_status is False:
            downtime_count += 1

    return downtime_count


def get_application_uptime(application):
    uptime_count = 0
    for availability_status in application.availability_history:
        if availability_status is True:
            uptime_count += 1

    return uptime_count


def display_simulation_metrics(simulation_parameters: dict, simulation_execution_time: float):
    application_raw_metrics = [
        {"name": "Uptime", "values": [get_application_downtime(application) for application in Application.all()]},
        {"name": "Downtime", "values": [get_application_uptime(application) for application in Application.all()]},
    ]
    application_metrics = {
        metric["name"]: {
            "min": min(metric["values"]),
            "max": max(metric["values"]),
            "avg": round(sum(metric["values"]) / len(metric["values"]), 2),
        }
        for metric in application_raw_metrics
    }

    # TODO: User perceived downtime is more complicated to calculate because each observation is a list of values, unlike the application metrics
    # user_raw_metrics = [
    #     {"name": "Perceived Downtime", "values": [user.user_perceived_downtime_history[str(user.applications[0].id)] for user in User.all()]},
    # ]
    # user_metrics = {
    #     metric["name"]: {
    #         "min": min(metric["values"]),
    #         "max": max(metric["values"]),
    #         "avg": round(sum(metric["values"]) / len(metric["values"]), 2),
    #     }
    #     for metric in user_raw_metrics
    # }

    metrics = {
        "Simulation Parameters": simulation_parameters,
        "Execution Time (seconds)": round(simulation_execution_time, 2),
        "Number of Applications/Services/Users": f"{Application.count()}/{Service.count()}/{User.count()}",
        "Number of Edge Servers": EdgeServer.count(),
        "Application Metrics": application_metrics,
    }

    print(dumps(metrics, indent=4))
