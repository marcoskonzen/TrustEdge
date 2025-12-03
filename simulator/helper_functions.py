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

class SimulationMetrics:
    """Class that encapsulates a set of metrics collected during the simulation execution."""
    
    def __init__(self):
        self.reset_all()
    
    def reset_all(self):
        """Resets all metrics to their initial state."""
        # SLA metrics
        self.sla_violations = 0
        self.delay_violations_per_delay_sla = {}
        self.delay_violations_per_access_pattern = {}

        # Infraestructure usage metrics
        self.total_overloaded_servers = 0
        self.total_occupation_steps = 0.0
        self.occupation_samples_per_model = {}
        self.total_power_consumption = 0.0
        self.power_samples_per_model = {}
        self.active_servers_per_model = {}
        self.simulation_steps = 0
        self.total_servers_per_model = {}
        self.available_occupation_steps = 0.0
        self.available_occupation_samples_per_model = {}

    def add_sla_violations(self, user_violations):
        """Adds SLA violations collected in the current step to the overall SLA violations.

        Args:
            user_violations (dict): Dictionary that contains the SLA violations collected in the current step.
        """
        # Acumular violações totais
        self.sla_violations += user_violations['delay_sla_violations']
        
        # Acumular violações por delay SLA
        for delay_sla, violations in user_violations['delay_violations_per_delay_sla'].items():
            self.delay_violations_per_delay_sla[delay_sla] = (
                self.delay_violations_per_delay_sla.get(delay_sla, 0) + violations
            )
        
        # Acumular violações por padrão de acesso
        for duration, violations in user_violations['delay_violations_per_access_pattern'].items():
            self.delay_violations_per_access_pattern[duration] = (
                self.delay_violations_per_access_pattern.get(duration, 0) + violations
            )

    def add_infrastructure_metrics(self, step_metrics):
        """Adiciona métricas de infraestrutura de um step às métricas globais."""
        # Incrementar contador de steps
        self.simulation_steps += 1

        # Armazenar o total de servidores por modelo
        if not self.total_servers_per_model:
            self.total_servers_per_model = step_metrics['total_servers_per_model'].copy()
        
        # Acumular servidores sobrecarregados
        self.total_overloaded_servers += step_metrics['overloaded_edge_servers']
        
        # Acumular ocupação geral
        self.total_occupation_steps += step_metrics['overall_occupation']

        # Acumular ocupação disponível
        self.available_occupation_steps += step_metrics['available_overall_occupation']

        # Acumular consumo de energia total
        self.total_power_consumption += step_metrics['overall_power_consumption']
        
        # Acumular ocupação por modelo
        for model_name, occupation in step_metrics['occupation_per_model'].items():
            if model_name not in self.occupation_samples_per_model:
                self.occupation_samples_per_model[model_name] = []
            self.occupation_samples_per_model[model_name].append(occupation)

        #Acumular ocupação por modelo (apenas servidores disponíveis)
        for model_name, occupation in step_metrics['available_occupation_per_model'].items():
            if model_name not in self.available_occupation_samples_per_model:
                self.available_occupation_samples_per_model[model_name] = []
            self.available_occupation_samples_per_model[model_name].append(occupation)
        
        # Acumular consumo por modelo
        for model_name, power_list in step_metrics['power_consumption_per_server_model'].items():
            if model_name not in self.power_samples_per_model:
                self.power_samples_per_model[model_name] = []
            self.power_samples_per_model[model_name].extend(power_list)
        
        # Acumular servidores ativos por modelo
        for model_name, active_count in step_metrics['active_servers_per_model'].items():
            if model_name not in self.active_servers_per_model:
                self.active_servers_per_model[model_name] = set()
            
            # Adicionar os IDs dos servidores ativos deste step
            for edge_server in EdgeServer.all():
                if (edge_server.model_name == model_name and 
                    edge_server.status == "available" and
                    (edge_server.cpu_demand > 0 or edge_server.memory_demand > 0 or edge_server.disk_demand > 0)):
                    self.active_servers_per_model[model_name].add(edge_server.id)
    
    def get_consolidated_metrics(self):
        """Retorna as métricas consolidadas da simulação."""
        # Calcular médias e totais
        avg_overall_occupation = (
            self.total_occupation_steps / self.simulation_steps 
            if self.simulation_steps > 0 else 0
        )
      
        # Calcular ocupação média por modelo
        avg_occupation_per_model = {}
        for model_name, samples in self.occupation_samples_per_model.items():
            avg_occupation_per_model[model_name] = sum(samples) / len(samples) if samples else 0
        
        # Calcular consumo de energia total por modelo
        total_power_per_model = {}
        for model_name, samples in self.power_samples_per_model.items():
            total_power_per_model[model_name] = sum(samples)

        #Calcular ocupação média por modelo (apenas servidores disponíveis)
        avg_available_occupation_per_model = {}
        for model_name, samples in self.available_occupation_samples_per_model.items():
            avg_available_occupation_per_model[model_name] = sum(samples) / len(samples) if samples else 0
        
        # Calcular média ponderada usando os valores por modelo e número de servidores
        total_weighted_available = 0
        total_servers = 0
        
        for model_name, avg_occupation in avg_available_occupation_per_model.items():
            servers_count = self.total_servers_per_model.get(model_name, 0)
            total_weighted_available += avg_occupation * servers_count
            total_servers += servers_count
        
        avg_available_overall_occupation = (
            total_weighted_available / total_servers 
            if total_servers > 0 else 0
        )
        
        # Converter sets de servidores ativos para contagens
        active_servers_count_per_model = {}
        for model_name, server_set in self.active_servers_per_model.items():
            active_servers_count_per_model[model_name] = len(server_set)

        # Coletar métricas de downtime NO FINAL da simulação
        user_total_perceived_downtime = 0
        total_perceived_downtime_per_access_pattern = {}
        total_perceived_downtime_per_delay_sla = {}
        total_violations_sla_downtime = 0
        total_violations_per_access_pattern = {}
        total_violations_per_delay_sla = {}

        for user in User.all():
            for app in user.applications:
                access_pattern = user.access_patterns[str(app.id)]
                duration = access_pattern.duration_values[0]
                delay_sla = user.delay_slas[str(app.id)]

                # Verificar se tem histórico de downtime
                if not hasattr(user, 'user_perceived_downtime_history'):
                    continue
                    
                if str(app.id) not in user.user_perceived_downtime_history:
                    continue
                
                downtime_history = user.user_perceived_downtime_history[str(app.id)]
                
                # Contar APENAS os True (downtime percebido quando usuário tentou acessar)
                perceived_downtime = sum(1 for status in downtime_history if status is True)
                
                # Debug para verificar
                total_access_attempts = len(downtime_history)
                successful_accesses = sum(1 for status in downtime_history if status is False)
                
                # print(f"[DEBUG METRICS] App {app.id}:")
                # print(f"                Total access attempts: {total_access_attempts}")
                # print(f"                Successful accesses: {successful_accesses}")
                # print(f"                Downtime occurrences: {perceived_downtime}")
                # print(f"                Downtime rate: {(perceived_downtime/total_access_attempts*100):.1f}%" if total_access_attempts > 0 else "                Downtime rate: 0%")
                
                user_total_perceived_downtime += perceived_downtime

                    
                if duration not in total_perceived_downtime_per_access_pattern:
                    total_perceived_downtime_per_access_pattern[duration] = 0
                total_perceived_downtime_per_access_pattern[duration] += perceived_downtime

                
                if delay_sla not in total_perceived_downtime_per_delay_sla:
                    total_perceived_downtime_per_delay_sla[delay_sla] = 0
                total_perceived_downtime_per_delay_sla[delay_sla] += perceived_downtime

                user_maximum_downtime_allowed = user.maximum_downtime_allowed[str(app.id)]
                
                if perceived_downtime > user_maximum_downtime_allowed:
                    app_violation = 1
                    total_violations_sla_downtime += app_violation

                    if duration not in total_violations_per_access_pattern:
                        total_violations_per_access_pattern[duration] = 0
                    total_violations_per_access_pattern[duration] += app_violation

                    if delay_sla not in total_violations_per_delay_sla:
                        total_violations_per_delay_sla[delay_sla] = 0
                    total_violations_per_delay_sla[delay_sla] += app_violation

                

        return {
            "total_simulation_steps": self.simulation_steps,
            "=========== SLA metrics ===========": None,
            "total_delay_sla_violations": self.sla_violations,
            "delay_violations_per_delay_sla": dict(self.delay_violations_per_delay_sla),
            "delay_violations_per_access_pattern": dict(self.delay_violations_per_access_pattern),
            "total_perceived_downtime": user_total_perceived_downtime,
            "total_perceived_downtime_per_access_pattern": dict(total_perceived_downtime_per_access_pattern),
            "total_perceived_downtime_per_delay_sla": dict(total_perceived_downtime_per_delay_sla),
            "total_downtime_sla_violations": total_violations_sla_downtime,
            "downtime_violations_per_access_pattern": dict(total_violations_per_access_pattern),
            "downtime_violations_per_delay_sla": dict(total_violations_per_delay_sla),

            "=========== Infrastructure metrics ===========": None,
            "total_servers_per_model": dict(self.total_servers_per_model),
            "total_overloaded_servers": self.total_overloaded_servers,
            "average_overall_occupation": avg_overall_occupation,
            "average_occupation_per_model": avg_occupation_per_model,
            "average_available_overall_occupation": avg_available_overall_occupation,
            "average_available_occupation_per_model": avg_available_occupation_per_model,
            "total_power_consumption": self.total_power_consumption,
            "total_power_consumption_per_model": total_power_per_model,
            
            
        }


_simulation_metrics = SimulationMetrics()


def get_simulation_metrics():
    """Retorna a instância das métricas de simulação."""
    return _simulation_metrics


def reset_all_counters():
    """Reseta todos os contadores globais."""
    _simulation_metrics.reset_all()


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

    path = nx.shortest_path(
        G=topology,
        source=origin_switch,
        target=target_switch,
        weight="delay",
    )
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
        if service.server:
            application_metadata = {
                "delay_sla": user.delay_slas[str(application.id)],
                "delay": user.delays[str(application.id)],
                "image": image.name,
                "state": service.state,
                "demand": [service.cpu_demand, service.memory_demand],
                "host": f"{service.server}. Model: {service.server.model_name} ({service.server.status})",
            }
        
        else:
            application_metadata = {
                "delay_sla": user.delay_slas[str(application.id)],
                "delay": user.delays[str(application.id)],
                "image": image.name,
                "state": service.state,
                "demand": [service.cpu_demand, service.memory_demand],
                "host": "Not placed",
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

    # path_delay = calculate_path_delay(
    #         origin_network_switch=user.base_station.network_switch, 
    #         target_network_switch=edge_server.network_switch
    #     )
    # # Adicionar delay wireless
    # wireless_delay = getattr(user.base_station, 'wireless_delay')
    # user.delays[str(application.id)] = wireless_delay + path_delay
    
    # path_delay = get_delay(
    #         wireless_delay=user.base_station.wireless_delay,
    #         origin_switch=user.base_station.network_switch,
    #         target_switch=edge_server.network_switch
    #         )
    
    user.set_communication_path(app=application)
    user._compute_delay(app=application, metric="latency")

    # DEBUG: Verificar se o delay foi atualizado
    print(f"[DEBUG] Delay pós-provisionamento App {application.id}: {user.delays[str(application.id)]}")

def deprovision_service(service, reason):
    """Libera recursos e remove o serviço da infraestrutura."""
    server = service.server
    if server is None and not hasattr(service, "_pending_origin_server"):
        return False

    print(f"[LOG] Desprovisionando serviço {service.id} do servidor {server.id if server else 'None'}")
    print(f"      Razão: {reason}")

    # Remover do servidor atual
    if server:
        cpu_before = server.cpu - server.cpu_demand
        mem_before = server.memory - server.memory_demand

        if service in server.services:
            server.services.remove(service)

        server.cpu_demand = max(0, server.cpu_demand - service.cpu_demand)
        server.memory_demand = max(0, server.memory_demand - service.memory_demand)

        cpu_after = server.cpu - server.cpu_demand
        mem_after = server.memory - server.memory_demand

        print(f"[LOG] ✓ Removido da lista do servidor {server.id}")
        print(f"[LOG] Recursos do servidor de origem {server.id}:")
        print(f"      ANTES: CPU disponível={cpu_before}, MEM disponível={mem_before}")
        print(f"      LIBERADO: CPU={service.cpu_demand}, MEM={service.memory_demand}")
        print(f"      DEPOIS: CPU disponível={cpu_after}, MEM disponível={mem_after}")

    # Limpar residual no servidor de origem (quando migração cancelada)
    pending_origin = getattr(service, "_pending_origin_server", None)
    if pending_origin and pending_origin is not server:
        if service in pending_origin.services:
            pending_origin.services.remove(service)

        pending_origin.cpu_demand = max(0, pending_origin.cpu_demand - service.cpu_demand)
        pending_origin.memory_demand = max(0, pending_origin.memory_demand - service.memory_demand)

        cpu_after = pending_origin.cpu - pending_origin.cpu_demand
        mem_after = pending_origin.memory - pending_origin.memory_demand

        print(f"[LOG] Recursos do servidor de origem {pending_origin.id}:")
        print(f"      DEPOIS DO AJUSTE: CPU disponível={cpu_after}, MEM disponível={mem_after}")

    # Limpar relacionamentos e flags
    service.server = None
    service._available = False
    if hasattr(service, "_pending_deprovision"):
        delattr(service, "_pending_deprovision")
    if hasattr(service, "_deprovision_reason"):
        delattr(service, "_deprovision_reason")
    if hasattr(service, "_pending_origin_server"):
        delattr(service, "_pending_origin_server")

    return True


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


def is_user_accessing_application(user, application, current_step):
    """Verifica se usuário está acessando aplicação no step atual."""
    app_id = str(application.id)
    
    if app_id not in user.access_patterns:
        return False
    
    access_pattern = user.access_patterns[app_id]
    if not access_pattern.history:
        return False
    
    last_access = access_pattern.history[-1]
    is_accessing = last_access["start"] <= current_step <= last_access["end"]
    
    return is_accessing


def get_sla_violations(user) -> dict:
    """Method that collects a set of SLA violation metrics for a given user."""
    
    delay_sla_violations = 0
    delay_violations_per_delay_sla = {}
    delay_violations_per_access_pattern = {}

    current_step = user.model.schedule.steps
    
    # Collecting delay SLA metrics
    for app in user.applications:
        if not is_user_accessing_application(user, app, current_step):
            continue

        user.set_communication_path(app=app)
        delay_sla = user.delay_slas[str(app.id)]
        delay = user._compute_delay(app=app, metric="latency")
        access_pattern = user.access_patterns[str(app.id)]
        duration = access_pattern.duration_values[0]
        
        # Calculating the number of delay SLA violations
        if delay > delay_sla:
            delay_sla_violations += 1
            
            if delay_sla not in delay_violations_per_delay_sla:
                delay_violations_per_delay_sla[delay_sla] = 0
            delay_violations_per_delay_sla[delay_sla] += 1
            
            if duration not in delay_violations_per_access_pattern:
                delay_violations_per_access_pattern[duration] = 0
            delay_violations_per_access_pattern[duration] += 1

    return {
        'delay_sla_violations': delay_sla_violations,
        'delay_violations_per_delay_sla': delay_violations_per_delay_sla,
        'delay_violations_per_access_pattern': delay_violations_per_access_pattern,
    }


def update_user_perceived_downtime_for_current_step(current_step):
    """
    Atualiza o downtime percebido por todos os usuários no step atual.
    
    Esta função deve ser chamada UMA VEZ por step por cada algoritmo.
    """
    print()
    print("=" * 70)
    print(f"[DEBUG_DOWNTIME] === MONITORANDO O DOWNTIME PERCEBIDO - STEP {current_step} ===")
    print("=" * 70)
    
    for user in User.all():
        # Inicializar histórico se não existir
        if not hasattr(user, "user_perceived_downtime_history"):
            user.user_perceived_downtime_history = {}
        
        for app in user.applications:
            app_id = str(app.id)
            
            # Inicializar histórico da aplicação se não existir
            if app_id not in user.user_perceived_downtime_history:
                user.user_perceived_downtime_history[app_id] = []
            
            # Verificar se usuário está fazendo requisição no step atual
            is_making_request = is_user_accessing_application(user, app, current_step)
            
            # SÓ REGISTRAR HISTÓRICO QUANDO USUÁRIO ESTÁ FAZENDO REQUISIÇÃO
            if is_making_request:
                service = app.services[0]
                is_migrating = False
                is_provisioning = False
                app_available = True
                
                if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
                    last_migration = service._Service__migrations[-1]

                    if last_migration["end"] is None:
                        if last_migration.get("origin") is None:
                            is_provisioning = True
                        else:
                            is_migrating = True
                
                

                if is_provisioning:
                    app_available = False
                    status = "PROVISIONAMENTO"
                elif is_migrating:
                    app_available = False
                    status = "MIGRAÇÃO"
                else:
                    # Verificar disponibilidade normal
                    for service in app.services:
                        if service.server:
                            if service.server.status != "available" or not service._available:
                                app_available = False
                                break
                        else:
                            app_available = False
                            break
                    status = "INDISPONÍVEL" if not app_available else "DISPONÍVEL"
                
                
                user.user_perceived_downtime_history[app_id].append(not app_available)
                
                if not app_available:
                    print(f"[DEBUG_DOWNTIME] App {app.id}: DOWNTIME PERCEBIDO ({status}) - Step {current_step}")
                else:
                    print(f"[DEBUG_DOWNTIME] App {app.id} (server {service.server.id if service.server else 'None'}): {status} - Step {current_step}")


def get_user_perceived_downtime_count(application):
    """
    Calcula o total de downtime percebido para uma aplicação específica.
    
    Args:
        application: Objeto da aplicação
        
    Returns:
        int: Número total de steps com downtime percebido por todos os usuários
    """
    total_perceived_downtime = 0
    
    for user in application.users:
        if (hasattr(user, "user_perceived_downtime_history") and 
            str(application.id) in user.user_perceived_downtime_history):
            # Contar apenas os valores True (downtime percebido)
            user_downtime = sum(1 for status in user.user_perceived_downtime_history[str(application.id)] if status)
            total_perceived_downtime += user_downtime
    
    return total_perceived_downtime


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
    """Calcula score de urgência por delay (MAIOR = mais urgente)."""
    user = app.users[0]
    delay_sla = user.delay_slas[str(app.id)]
    current_delay = user.delays[str(app.id)] if user.delays[str(app.id)] is not None else 0
    
    # 1. Urgência baseada na proximidade da violação
    delay_urgency = max(0, current_delay / delay_sla) if delay_sla > 0 else 0
    
    # 2. Escassez de recursos (poucos servidores adequados = maior urgência)
    user_switch = user.base_station.network_switch
    available_servers = [s for s in EdgeServer.all() if s.status == "available"]
    
    suitable_servers = 0
    for edge_server in available_servers:
        server_delay = calculate_path_delay(
            origin_network_switch=user_switch, 
            target_network_switch=edge_server.network_switch
        )
        if server_delay <= delay_sla:
            suitable_servers += 1
    
    # Escassez: poucos servidores = maior score
    if suitable_servers == 0:
        scarcity_factor = 10.0  # Score alto mas finito para indicar escassez total
    else:
        scarcity_factor = 1.0 / suitable_servers
    
    # Combinar urgência e escassez
    delay_score = (delay_urgency * 2.0) + scarcity_factor
    
    return delay_score

def get_application_access_intensity_score(app: object) -> float:
    """Calcula score de intensidade de acesso (MAIOR = mais intenso)."""
    user = app.users[0]
    access_pattern = user.access_patterns[str(app.id)]
    
    duration = access_pattern.duration_values[0]
    interval = access_pattern.interval_values[0]
    
    # Frequência de acesso (quanto menor o intervalo, maior a frequência)
    frequency_score = 1.0 / interval if interval > 0 else 1.0
    
    # Duração do acesso (quanto maior, mais importante)
    duration_score = duration / 100.0  # Normalizar para escala razoável
    
    # Combinar frequência e duração
    base_score = (frequency_score * duration_score)
    
    # Aplicar transformação logarítmica para suavizar
    intensity_score = math.log(1 + base_score) * 10
    
    return intensity_score

def get_host_candidates(user: object, service: object) -> list:
    """Obtém lista de candidatos para hospedar serviço."""
    host_candidates = []

    app = service.application
    user = app.users[0]

    available_servers = [s for s in EdgeServer.all() 
                        if s.status == "available" and get_normalized_free_capacity(s) > 0]
    
    for edge_server in available_servers:
        # Calcular delay e violações SLA
        path_delay = get_delay(
            wireless_delay=user.base_station.wireless_delay,
            origin_switch=user.base_station.network_switch,
            target_switch=edge_server.network_switch
            )
        
        sla_violations = 1 if path_delay > user.delay_slas[str(service.application.id)] else 0
        
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
            "overall_delay": path_delay,
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
    return get_user_perceived_downtime_count(application)


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
    
    # # Métricas da fila de espera
    # waiting_queue_metrics = {
    #     "Total Applications in Queue": len(_waiting_queue),
    #     "Applications by Priority": {}
    # }
    
    # if _waiting_queue:
    #     priorities = {}
    #     for item in _waiting_queue:
    #         priority = int(item["priority_score"] // 100)  # Agrupa por centenas
    #         priorities[priority] = priorities.get(priority, 0) + 1
    #     waiting_queue_metrics["Applications by Priority"] = priorities
    
    metrics = {
        "Simulation Parameters": simulation_parameters,
        "Infrastructure": f"{Application.count()}/{Service.count()}/{User.count()}/{EdgeServer.count()}",
        #"Waiting Queue": waiting_queue_metrics,
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


# ============================================================================
# INFRASTRUCTURE COLLECTION FUNCTIONS
# ============================================================================
def get_infrastructure_usage_metrics() -> dict:
    """Method that collects a set of infrastructure metrics."""
    
    # Declaring infrastructure metrics
    overloaded_edge_servers = 0
    overall_occupation = 0
    occupation_per_model = {}
    overall_power_consumption = 0
    power_consumption_per_server_model = {}
    active_servers_per_model = {}
    total_servers_per_model = {}
    available_overall_occupation = 0
    available_occupation_per_model = {}
    available_servers_per_model = {}

    # Counter total servers per model
    for edge_server in EdgeServer.all():
        if edge_server.model_name not in total_servers_per_model:
            total_servers_per_model[edge_server.model_name] = 0
        total_servers_per_model[edge_server.model_name] += 1
        
        if edge_server.model_name not in occupation_per_model:
            occupation_per_model[edge_server.model_name] = 0

        # Inicializar ocupação para servidores disponíveis
        if edge_server.model_name not in available_occupation_per_model:
            available_occupation_per_model[edge_server.model_name] = 0
        
        # Contar servidores disponíveis por modelo
        if edge_server.status == "available":
            if edge_server.model_name not in available_servers_per_model:
                available_servers_per_model[edge_server.model_name] = 0
            available_servers_per_model[edge_server.model_name] += 1

    # Collecting infrastructure metrics
    for edge_server in EdgeServer.all():
        if edge_server.status == "available":
        
            # Overall Occupation
            capacity = normalize_cpu_and_memory(cpu=edge_server.cpu, memory=edge_server.memory)
            demand = normalize_cpu_and_memory(cpu=edge_server.cpu_demand, memory=edge_server.memory_demand)
            server_occupation = demand / capacity * 100
            overall_occupation += server_occupation
            available_overall_occupation += server_occupation
            overall_power_consumption += edge_server.get_power_consumption()

            # Number of overloaded edge servers
            free_cpu = edge_server.cpu - edge_server.cpu_demand
            free_memory = edge_server.memory - edge_server.memory_demand
            free_disk = edge_server.disk - edge_server.disk_demand
            if free_cpu < 0 or free_memory < 0 or free_disk < 0:
                overloaded_edge_servers += 1

            # Occupation per Server Model
            occupation_per_model[edge_server.model_name] += server_occupation
            available_occupation_per_model[edge_server.model_name] += server_occupation

            # Power consumption per Server Model
            if edge_server.model_name not in power_consumption_per_server_model.keys():
                power_consumption_per_server_model[edge_server.model_name] = []
            power_consumption_per_server_model[edge_server.model_name].append(edge_server.get_power_consumption())

            # Active servers per model (servers with any demand > 0)
            if edge_server.cpu_demand > 0 or edge_server.memory_demand > 0 or edge_server.disk_demand > 0:
                if edge_server.model_name not in active_servers_per_model:
                    active_servers_per_model[edge_server.model_name] = set()
                active_servers_per_model[edge_server.model_name].add(edge_server.id)

    # Aggregating overall metrics for this step
    overall_occupation = overall_occupation / EdgeServer.count() if EdgeServer.count() > 0 else 0

    # Convert occupation per model to averages for this step
    for model_name in occupation_per_model.keys():
        total_servers = total_servers_per_model[model_name]
        occupation_per_model[model_name] = occupation_per_model[model_name] / total_servers if total_servers > 0 else 0

    # Calcular available_overall_occupation como média ponderada
    total_weighted_occupation = 0
    total_available_servers = 0
    
    for model_name in available_occupation_per_model.keys():
        available_servers_for_model = available_servers_per_model.get(model_name, 0)
        if available_servers_for_model > 0:
            # Ocupação média deste modelo
            model_avg_occupation = available_occupation_per_model[model_name] / available_servers_for_model
            available_occupation_per_model[model_name] = model_avg_occupation
            
            # Contribuir para média ponderada global
            total_weighted_occupation += model_avg_occupation * available_servers_for_model
            total_available_servers += available_servers_for_model
        else:
            available_occupation_per_model[model_name] = 0
    
    # Ocupação geral disponível (média ponderada)
    available_overall_occupation = (
        total_weighted_occupation / total_available_servers 
        if total_available_servers > 0 else 0
    )

    # Convert active servers sets to counts
    for model_name in active_servers_per_model.keys():
        active_servers_per_model[model_name] = len(active_servers_per_model[model_name])

    metrics = {
        "overloaded_edge_servers": overloaded_edge_servers,
        "overall_occupation": overall_occupation,
        "occupation_per_model": occupation_per_model,
        "overall_power_consumption": overall_power_consumption,
        "power_consumption_per_server_model": power_consumption_per_server_model,
        "active_servers_per_model": active_servers_per_model,
        "total_servers_per_model": total_servers_per_model,
        "available_overall_occupation": available_overall_occupation,
        "available_occupation_per_model": available_occupation_per_model,
    }

    return metrics


def collect_infrastructure_metrics_for_current_step():
    """Coleta as métricas de infraestrutura do step atual e acumula nas métricas globais."""
    metrics = get_simulation_metrics()
    step_metrics = get_infrastructure_usage_metrics()
    metrics.add_infrastructure_metrics(step_metrics)


def collect_sla_violations_for_current_step():
    """Coleta as violações de SLA do step atual e acumula nas métricas globais."""
    metrics = get_simulation_metrics()
    
    for user in User.all():
        user_sla_violations = get_sla_violations(user)
        metrics.add_sla_violations(user_sla_violations)


def topology_collect(self) -> dict:
    """Method that collects a set of metrics for the object.

    The network topology aggregates the following metrics from the simulation:
        1. Infrastructure Usage
            - Overall Occupation
            - Occupation per Infrastructure Provider
            - Occupation per Server Model
            - Active Servers per Model
            - Power Consumption
                - Overall Power Consumption
                - Power Consumption per Server Model
        2. SLA Violations
            - Number of Delay SLA Violations
            - Number of Delay Violations per Delay SLA
            - Number of Delay Violations per Access Pattern
        3. Availability
            - Total Perceived Downtime by Users
            - Total Perceived Downtime per Access Pattern

    Returns:
        metrics (dict): Object metrics.
    """
    
    # Obter métricas consolidadas
    consolidated_metrics = get_simulation_metrics().get_consolidated_metrics()

    # Combinar todas as métricas
    metrics = {
        **consolidated_metrics,  # Métricas SLA e infraestrutura
    }

    return metrics