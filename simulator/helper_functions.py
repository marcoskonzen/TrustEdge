"""This file contains a set of helper functions that facilitate the simulation execution."""

# Importing Python libraries
from random import choice, shuffle, sample
import matplotlib.pyplot as plt
import networkx as nx
from json import dumps
from random import sample, randint
import math  # Adicionado para cálculos matemáticos mais precisos
from math import isinf, sqrt
import numpy as np
from scipy import stats

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
        self.total_delay_sla_violations = 0 
        self.sla_violations = 0
        self.delay_violations_per_delay_sla = {}
        self.delay_violations_per_access_pattern = {}
        self.delay_violations_per_application = {}
        self.total_perceived_downtime = 0

        # Downtime Reasons Metrics (NOVO)
        self.downtime_reasons = {}

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
        self.total_delay_sla_violations += user_violations['delay_sla_violations']  # ✅ ADICIONAR
        
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
    
    def add_downtime_reason(self, reason):
        """Incrementa o contador para um motivo específico de downtime."""
        if reason not in self.downtime_reasons:
            self.downtime_reasons[reason] = 0
        self.downtime_reasons[reason] += 1

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
            num_servers = self.total_servers_per_model.get(model_name, 0)
            total_weighted_available += avg_occupation * num_servers
            total_servers += num_servers
        
        avg_available_overall_occupation = (
            total_weighted_available / total_servers 
            if total_servers > 0 else 0
        )
        
        # Converter sets de servidores ativos para contagens
        active_servers_count_per_model = {}
        for model_name, server_set in self.active_servers_per_model.items():
            active_servers_count_per_model[model_name] = len(server_set)

        # ═══════════════════════════════════════════════════════════════
        # ✅ CORREÇÃO: USAR downtime_reasons COMO FONTE DE VERDADE
        # ═══════════════════════════════════════════════════════════════
        # O downtime REAL é a soma de todos os registros em downtime_reasons
        user_total_perceived_downtime = sum(self.downtime_reasons.values())
        
        # ═══════════════════════════════════════════════════════════════
        # ✅ CORREÇÃO: CALCULAR VIOLAÇÕES DE SLA DE DOWNTIME POR SESSÃO
        # ═══════════════════════════════════════════════════════════════
        total_perceived_downtime_per_access_pattern = {}
        total_perceived_downtime_per_delay_sla = {}
        total_violations_sla_downtime = 0
        apps_violations_sla_downtime = []
        total_violations_per_access_pattern = {}
        total_violations_per_delay_sla = {}

        # ✅ NOVO: Mapear downtime_reasons para access_pattern e delay_sla
        # Como downtime_reasons não tem app_id, precisamos extrair de Service.all()
        
        # Primeiro, criar mapeamento service_id -> (app_id, access_pattern, delay_sla)
        service_metadata = {}
        for user in User.all():
            for app in user.applications:
                app_id = str(app.id)
                service = app.services[0]
                
                access_pattern = user.access_patterns[app_id]
                duration = access_pattern.duration_values[0] if access_pattern.duration_values else 0
                delay_sla = user.delay_slas[app_id]
                downtime_sla = user.maximum_downtime_allowed.get(app_id, float('inf'))
                
                service_metadata[service.id] = {
                    'app_id': app_id,
                    'user': user,
                    'access_pattern_duration': duration,
                    'delay_sla': delay_sla,
                    'downtime_sla': downtime_sla,
                    'access_history': access_pattern.history
                }
        
        # ✅ Processar downtime_reasons e acumular por access_pattern/delay_sla
        # IMPORTANTE: downtime_reasons tem formato "categoria_detalhada"
        # Mas NÃO tem service_id diretamente. Precisamos de outra abordagem.
        
        # ✅ ALTERNATIVA: Iterar sobre SERVIÇOS e suas migrações/provisionamentos
        for service in Service.all():
            if service.id not in service_metadata:
                continue  # Serviço sem usuário associado
            
            meta = service_metadata[service.id]
            app_id = meta['app_id']
            user = meta['user']
            duration = meta['access_pattern_duration']
            delay_sla = meta['delay_sla']
            downtime_sla = meta['downtime_sla']
            access_history = meta['access_history']
            
            # Obter histórico de downtime percebido (se existir)
            if hasattr(user, '_perceived_downtime') and app_id in user._perceived_downtime:
                total_downtime_for_app = user._perceived_downtime[app_id]
                
                # Acumular por access_pattern e delay_sla
                if duration not in total_perceived_downtime_per_access_pattern:
                    total_perceived_downtime_per_access_pattern[duration] = 0
                total_perceived_downtime_per_access_pattern[duration] += total_downtime_for_app
                
                if delay_sla not in total_perceived_downtime_per_delay_sla:
                    total_perceived_downtime_per_delay_sla[delay_sla] = 0
                total_perceived_downtime_per_delay_sla[delay_sla] += total_downtime_for_app
                
                # ✅ Analisar SESSÕES INDIVIDUAIS para violações de SLA
                for session in access_history:
                    session_start = session.get('start')
                    session_end = session.get('end')
                    
                    if session_start is None or session_end is None:
                        continue
                    
                    # Calcular downtime NESTA SESSÃO específica
                    # PROBLEMA: _perceived_downtime[app_id] é um CONTADOR TOTAL, não histórico por step
                    # Solução: Se houver user_perceived_downtime_history, usar ele
                    session_downtime = 0
                    
                    if (hasattr(user, 'user_perceived_downtime_history') and 
                        app_id in user.user_perceived_downtime_history):
                        downtime_history = user.user_perceived_downtime_history[app_id]
                        
                        # Contar downtime durante esta sessão
                        for step in range(session_start, session_end + 1):
                            step_index = step - 1  # Histórico começa em índice 0
                            if step_index < len(downtime_history):
                                if downtime_history[step_index]:  # True = downtime
                                    session_downtime += 1
                    
                    # ✅ VERIFICAR SE ESTA SESSÃO VIOLOU O SLA DE DOWNTIME
                    if session_downtime > downtime_sla:
                        total_violations_sla_downtime += 1
                        
                        # Adicionar app à lista de violadores (sem duplicar)
                        if app_id not in apps_violations_sla_downtime:
                            apps_violations_sla_downtime.append(app_id)
                        
                        # Contabilizar por access pattern
                        if duration not in total_violations_per_access_pattern:
                            total_violations_per_access_pattern[duration] = 0
                        total_violations_per_access_pattern[duration] += 1
                        
                        # Contabilizar por delay SLA
                        if delay_sla not in total_violations_per_delay_sla:
                            total_violations_per_delay_sla[delay_sla] = 0
                        total_violations_per_delay_sla[delay_sla] += 1

        return {
            "total_simulation_steps": self.simulation_steps,
            "=========== SLA metrics ===========": None,
            "total_delay_sla_violations": self.total_delay_sla_violations,
            "delay_violations_per_delay_sla": dict(self.delay_violations_per_delay_sla),
            "delay_violations_per_access_pattern": dict(self.delay_violations_per_access_pattern),
            "total_perceived_downtime": user_total_perceived_downtime,
            "total_perceived_downtime_per_access_pattern": dict(total_perceived_downtime_per_access_pattern),
            "total_perceived_downtime_per_delay_sla": dict(total_perceived_downtime_per_delay_sla),
            "total_downtime_sla_violations": total_violations_sla_downtime,
            "apps_violations_sla_downtime": apps_violations_sla_downtime,   
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

            "=========== Downtime Analysis ===========": None,
            "downtime_reasons": dict(self.downtime_reasons),
        }


_simulation_metrics = SimulationMetrics()
_predict_failures_log_guard = set()

def _cleanup_predict_failures_log_guard(current_step):
    """Limpa guard de logs de previsões antigas."""
    global _predict_failures_log_guard
    
    if current_step % 100 == 0:
        cutoff = current_step - 100
        _predict_failures_log_guard = {k for k in _predict_failures_log_guard if k[0] >= cutoff}
        
        # ✅ Log opcional (comentar em produção)
        # print(f"[CLEANUP] Guard de predict_failures limpo (mantendo últimos 100 steps)")


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


# ============================================================================
# NETWORK AWARENESS HELPER (NEW)
# ============================================================================

def get_path_bottleneck(topology, source_node, target_node):
    """
    Calculates the available bandwidth (bottleneck) on the shortest path between two nodes.
    Returns value in MB/s.
    """
    try:
        # EdgeSimPy uses shortest path by default
        path = nx.shortest_path(topology, source=source_node, target=target_node)
        
        min_available_bw = float('inf')
        
        # Iterate over links in the path
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i+1]
            
            # Get link data from NetworkX graph
            edge_data = topology.get_edge_data(u, v)
            
            if edge_data:
                # Try to access the NetworkLink object directly
                link_obj = edge_data.get('object')
                
                if link_obj:
                    # Real-time calculation: Capacity - Current Demand
                    available = link_obj.bandwidth - link_obj.bandwidth_demand
                else:
                    # Fallback to metadata
                    bandwidth = edge_data.get('bandwidth', 12.5) # Default 100Mbps = 12.5MB/s
                    demand = edge_data.get('bandwidth_demand', 0)
                    available = bandwidth - demand
                
                if available < min_available_bw:
                    min_available_bw = available
        
        # If path is just the node itself (local), return infinite or max internal speed
        if min_available_bw == float('inf'):
            return 125.0 # 1000 Mbps (internal)
            
        return max(0.1, min_available_bw) # Avoid division by zero

    except (nx.NetworkXNoPath, Exception):
        return 0.1 # Return minimal bandwidth on error


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
        # Só conta se o usuário está acessando
        if not is_user_accessing_application(user, app, current_step):
            continue

        service = app.services[0]
        delay_sla = user.delay_slas[str(app.id)]
        access_pattern = user.access_patterns[str(app.id)]
        duration = access_pattern.duration_values[0]

        # 🛑 CORREÇÃO CRÍTICA:
        # Se o serviço não tem servidor OU o servidor está FALHO/DESLIGADO/BOOTING
        # O delay é INFINITO (serviço inacessível).
        # Antes, isso calculava apenas "latência de rede", ignorando que o servidor estava morto.
        if not service.server or not service.server.available:
            delay = float('inf')
        else:
            user.set_communication_path(app=app)
            delay = user._compute_delay(app=app, metric="latency")
        
        # Lógica de Live Migration (Opcional, para refinar):
        # Se for Live Migration, o service.server aponta para ORIGEM.
        # Se a origem está viva (server.available=True), o delay acima (calculado para origem) está CORRETO.
        # Então não precisamos de lógica extra aqui, o check de 'service.server.available' já cobre.

        if delay > delay_sla or isinf(delay):
            delay_sla_violations += 1
            # ...existing code... (contabilização nos dicionários)
            delay_violations_per_delay_sla[delay_sla] = delay_violations_per_delay_sla.get(delay_sla, 0) + 1
            delay_violations_per_access_pattern[duration] = delay_violations_per_access_pattern.get(duration, 0) + 1

    return {
        'delay_sla_violations': delay_sla_violations,
        'delay_violations_per_delay_sla': delay_violations_per_delay_sla,
        'delay_violations_per_access_pattern': delay_violations_per_access_pattern,
    }


def update_user_perceived_downtime_for_current_step(current_step):
    """
    Atualiza downtime percebido de forma CENTRALIZADA e CONSISTENTE.
    
    REGRAS CORRIGIDAS:
    1. Downtime SOMENTE quando delay = inf E usuário está acessando
    2. Classificar causa usando is_service_available_for_user()
    3. Contabilizar por usuário e globalmente
    """
    
    metrics = get_simulation_metrics()
    total_downtime_this_step = 0
    
    # ✅ REMOVER logs excessivos (só manter se DEBUG ativo)
    DEBUG_DOWNTIME = False  # Alterar para True se precisar debugar
    
    if DEBUG_DOWNTIME:
        print(f"\n{'='*70}")
        print(f"[DEBUG_DOWNTIME] === MONITORANDO O DOWNTIME PERCEBIDO - STEP {current_step} ===")
        print(f"{'='*70}")
    
    for user in User.all():
        if not hasattr(user, '_perceived_downtime'):
            user._perceived_downtime = {}
        
        # ✅ GARANTIR: Inicializar user_perceived_downtime_history
        if not hasattr(user, 'user_perceived_downtime_history'):
            user.user_perceived_downtime_history = {}
        
        for app in user.applications:
            app_id = str(app.id)
            service = app.services[0]
            
            # ✅ GARANTIR: Inicializar histórico para este app
            if app_id not in user.user_perceived_downtime_history:
                user.user_perceived_downtime_history[app_id] = []
            
            # ✅ REGRA: Só conta downtime se usuário ESTÁ acessando
            if not is_user_accessing_application(user, app, current_step):
                # ✅ IMPORTANTE: Adicionar False ao histórico mesmo quando não está acessando
                # Isso mantém sincronização entre step e índice do array
                user.user_perceived_downtime_history[app_id].append(False)
                continue
            
            # ✅ Verificar disponibilidade
            is_available, unavailability_reason = is_service_available_for_user(
                service, user, app, current_step
            )
            
            # ✅ CRÍTICO: Adicionar ao histórico (True = downtime, False = disponível)
            user.user_perceived_downtime_history[app_id].append(not is_available)
            
            if not is_available:
                # ✅ DOWNTIME DETECTADO
                total_downtime_this_step += 1
                
                # Contabilizar por usuário (para compatibilidade)
                if app_id not in user._perceived_downtime:
                    user._perceived_downtime[app_id] = 0
                user._perceived_downtime[app_id] += 1
                
                # ✅ Classificar causa DETALHADA
                detailed_cause = _classify_downtime_cause_v2(
                    user, app, service, current_step, unavailability_reason
                )
                
                # Contabilizar globalmente por causa
                if detailed_cause not in metrics.downtime_reasons:
                    metrics.downtime_reasons[detailed_cause] = 0
                metrics.downtime_reasons[detailed_cause] += 1
                
                # ✅ LOG (só primeiras 3 ocorrências de cada causa)
                if DEBUG_DOWNTIME and metrics.downtime_reasons[detailed_cause] <= 3:
                    server_info = f"{service.server.id} (disponível: {service.server.available})" if service.server else "None"
                    
                    print(f"[DEBUG_DOWNTIME] User {user.id} | App {app.id} | Service {service.id}")
                    print(f"                 Causa: {detailed_cause}")
                    print(f"                 Delay atual: {user.delays.get(app_id, 0)}")
                    print(f"                 Status serviço: available={service._available}")
                    print(f"                 Servidor: {server_info}")
    
    # ✅ Atualizar total global
    metrics.total_perceived_downtime += total_downtime_this_step
    
    if DEBUG_DOWNTIME:
        print(f"{'='*70}\n")
    
    # ✅ Log periódico (simplificado)
    if current_step % 100 == 0 and total_downtime_this_step > 0:
        print(f"[DOWNTIME_SUMMARY] Step {current_step}: {total_downtime_this_step} steps de downtime")
        print(f"                   Total acumulado: {metrics.total_perceived_downtime}")


def _classify_downtime_cause(user, app, service, current_step):
    """
    Classifica causa do downtime em categorias detalhadas.
    
    Retorna string com a categoria (ex: "migration_downloading_layers").
    """
    # Verificar se há migração ativa
    if hasattr(service, '_Service__migrations') and service._Service__migrations:
        migration = service._Service__migrations[-1]
        
        if migration.get("end") is None:  # Migração ativa
            status = migration.get("status", "unknown")
            origin = migration.get("origin")
            
            # ✅ CORRIGIDO: Usar original_migration_reason com fallback robusto
            original_reason = migration.get("original_migration_reason")
            
            # ✅ FALLBACK: Se original_reason for None/vazio, tentar inferir
            if not original_reason or original_reason == "unknown":
                migration_reason = migration.get("migration_reason", "unknown")
                
                # Tentar inferir da migration_reason
                if migration_reason == "server_failed":
                    # Verificar se é Cold Migration
                    if migration.get("is_cold_migration", False):
                        original_reason = "server_failed_unpredicted"
                    elif migration.get("is_recovery_after_prevention", False):
                        original_reason = "low_reliability"  # Assumir low_reliability como padrão
                    else:
                        original_reason = "server_failed_unpredicted"  # Conservador
                else:
                    original_reason = migration_reason if migration_reason else "unknown"
                
                # ✅ LOG DE DEBUG
                print(f"[CLASSIFY_DOWNTIME] ⚠️ original_reason vazio! Inferido: '{original_reason}' (migration_reason: '{migration_reason}')")
            
            # ✅ MIGRAÇÃO ATIVA
            if origin is None:
                # PROVISIONAMENTO
                if status == "waiting":
                    # ✅ Verificar se está na fila de espera GLOBAL
                    from simulator.algorithms.trust_edge_v3 import is_application_in_waiting_queue
                    if is_application_in_waiting_queue(app.id):
                        return "provisioning_waiting_in_global_queue"
                    else:
                        return "provisioning_waiting_in_download_queue"
                
                elif status == "pulling_layers":
                    return "provisioning_downloading_layers"
                
                else:
                    return "provisioning_other"
            
            else:
                # MIGRAÇÃO (origin != None)
                
                if status == "waiting":
                    # ✅ Verificar se está na fila de espera GLOBAL
                    from simulator.algorithms.trust_edge_v3 import is_application_in_waiting_queue
                    if is_application_in_waiting_queue(app.id):
                        return f"migration_{original_reason}_waiting_in_global_queue"
                    else:
                        return f"migration_{original_reason}_waiting_in_download_queue"
                
                elif status == "pulling_layers":
                    # Cold migration (origem indisponível)
                    if not origin.available:
                        return f"migration_{original_reason}_downloading_layers_cold"
                    else:
                        # Não deveria estar indisponível (Live Migration)
                        return f"migration_{original_reason}_downloading_layers_live_error"
                
                elif status == "migrating_service_state":
                    return f"migration_{original_reason}_cutover"
                
                else:
                    return f"migration_{original_reason}_other"
    
    # ✅ SEM MIGRAÇÃO ATIVA → Serviço órfão ou servidor falhou
    if service.server is None or not service.server.available:
        # Verificar se está na fila de espera
        from simulator.algorithms.trust_edge_v3 import is_application_in_waiting_queue
        if is_application_in_waiting_queue(app.id):
            return "server_failure_orphaned_in_queue"
        else:
            return "server_failure_orphaned_no_migration_yet"
    
    # ✅ CASO NÃO CLASSIFICADO
    return "downtime_unclassified"

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
# FAILURE RELIABILITY TRACKING (Reliability at failure instant)
# ============================================================================

_failure_reliability_events = []   # [{server_id, step, reliability_pct}]
_failure_reliability_seen = set()  # {(server_id, failure_start_step)}

def init_failure_reliability_tracking():
    """Reseta buffers de rastreamento de confiabilidade em falhas."""
    global _failure_reliability_events, _failure_reliability_seen
    _failure_reliability_events = []
    _failure_reliability_seen = set()

def record_server_failure_reliability(current_step, horizon=50):
    """
    Registra a confiabilidade do servidor no exato step em que a falha inicia.
    Usa failure_trace (planejado) para identificar o início da falha.
    """
    for server in EdgeServer.all():
        # Flatten do trace de falhas
        if not hasattr(server, "failure_model") or not server.failure_model.failure_trace:
            continue

        flatten_trace = [f for group in server.failure_model.failure_trace for f in group]
        for failure in flatten_trace:
            starts_at = failure["failure_starts_at"]
            # Apenas falhas que começam neste step e que ainda não foram registradas
            if starts_at != current_step or starts_at < 0:
                continue

            key = (server.id, starts_at)
            if key in _failure_reliability_seen:
                continue

            reliability_pct = get_server_conditional_reliability_weibull(server, horizon) 
            _failure_reliability_events.append({
                "server_id": server.id,
                "step": starts_at,
                "reliability_pct": reliability_pct
            })
            _failure_reliability_seen.add(key)

def print_failure_reliability_summary():
    """
    Exibe, ao final da simulação, a confiabilidade dominante no momento das falhas.
    """
    if not _failure_reliability_events:
        print("\n[FAILURE_RELIABILITY] Nenhuma falha registrada.")
        return

    # Histograma GLOBAL por faixa de 10%
    global_bins = {f"{i*10}-{i*10+10}%": 0 for i in range(10)}
    # Histograma POR SERVIDOR
    per_server_bins = {}  # server_id -> {bucket_label: count}

    for evt in _failure_reliability_events:
        bucket = min(9, int(evt["reliability_pct"] // 10))
        label = f"{bucket*10}-{bucket*10+10}%"
        global_bins[label] += 1

        sid = evt["server_id"]
        if sid not in per_server_bins:
            per_server_bins[sid] = {f"{i*10}-{i*10+10}%": 0 for i in range(10)}
        per_server_bins[sid][label] += 1

    global_dominant_bucket = max(global_bins.items(), key=lambda x: x[1])

    print("\n" + "="*70)
    print("[FAILURE_RELIABILITY] CONFIABILIDADE NO MOMENTO DAS FALHAS")
    print("="*70)

    # Faixa dominante por servidor
    print("\n[FAILURE_RELIABILITY] Faixa dominante POR SERVIDOR:")
    for sid in sorted(per_server_bins.keys()):
        bins = per_server_bins[sid]
        dominant = max(bins.items(), key=lambda x: x[1])
        if dominant[1] == 0:
            # nenhum evento registrado para este servidor (só por segurança)
            continue
        print(f"  - Servidor {sid}: faixa dominante {dominant[0]} (ocorrências: {dominant[1]})")

    # Histograma global (para referência)
    print("\n[FAILURE_RELIABILITY] Histograma global por faixa de 10%:")
    for label, count in global_bins.items():
        if count > 0:
            print(f"  {label}: {count}")

    print(f"\n[FAILURE_RELIABILITY] Faixa global dominante: {global_dominant_bucket[0]} (ocorrências: {global_dominant_bucket[1]})")
    print("="*70)


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
    """
    Retorna tempo desde a última recuperação.
    
    ✅ CORREÇÃO: Para servidores que nunca falharam na simulação atual,
    usa o tempo desde a última falha do HISTÓRICO.
    """
    current_step = server.model.schedule.steps + 1
    
    # Verificar se tem falhas no histórico da SIMULAÇÃO ATUAL
    if hasattr(server, 'failure_model') and server.failure_model.failure_history:
        # Obter última falha do histórico
        last_failure = server.failure_model.failure_history[-1]
        
        # Se a falha está no PASSADO (histórico pré-carregado)
        if last_failure['becomes_available_at'] < 0:
            # Servidor nunca falhou na simulação atual
            # Usar tempo desde o início da simulação
            return current_step
        
        # Se já falhou na simulação atual
        if last_failure['becomes_available_at'] < current_step:
            return current_step - last_failure['becomes_available_at']
        
        # Se está em falha AGORA
        if last_failure['failure_starts_at'] <= current_step < last_failure['becomes_available_at']:
            return 0  # Acabou de falhar
    
    # Fallback: Servidor nunca falhou (nem no histórico)
    # Retornar tempo desde início da simulação
    return current_step


def get_server_availability(server: object) -> float:
    """
    Calcula disponibilidade histórica do servidor.
    
    Availability = MTBF / (MTBF + MTTR)
    """
    mtbf = get_server_mtbf(server)
    mttr = get_server_mttr(server)
    
    if mtbf == float('inf'):
        return 100.0
    
    if mtbf + mttr == 0:
        return 0.0
    
    availability = (mtbf / (mtbf + mttr)) * 100
    return availability


# ============================================================================
# WEIBULL PARAMETER ESTIMATION (MLE from History)
# ============================================================================

def estimate_weibull_parameters_from_history(server, window_size=10):
    """
    Estima parâmetros Weibull usando janela deslizante das N falhas mais recentes.
    
    Args:
        server: Servidor a analisar
        window_size: Número de falhas mais recentes a considerar (padrão: 10)
    
    Returns:
        dict: Parâmetros estimados com metadados de qualidade
    """
    if not hasattr(server, 'failure_model') or not server.failure_model:
        return _default_weibull_params()
    
    failure_history = server.failure_model.failure_history
    
    if not failure_history or len(failure_history) < 2:
        return _default_weibull_params()
    
    # ✅ NOVO: Usar apenas as N falhas mais recentes (janela deslizante)
    sorted_failures = sorted(failure_history, key=lambda f: f['failure_starts_at'])
    recent_failures = sorted_failures[-window_size:] if len(sorted_failures) > window_size else sorted_failures
    
    tbf_data = []
    ttr_data = []
    
    for i in range(len(recent_failures)):
        current_failure = recent_failures[i]
        
        # Tempo de reparo (TTR)
        ttr = current_failure['becomes_available_at'] - current_failure['failure_starts_at']
        if ttr > 0:
            ttr_data.append(ttr)
        
        # Tempo entre falhas (TBF)
        if i > 0:
            previous_failure = recent_failures[i-1]
            tbf = current_failure['failure_starts_at'] - previous_failure['becomes_available_at']
            if tbf > 0:
                tbf_data.append(tbf)
    
    if len(tbf_data) < 2:
        return _default_weibull_params()
    
    # Estimação via Maximum Likelihood (MLE)
    try:
        tbf_array = np.array(tbf_data)
        shape_c, loc, scale_lambda = stats.weibull_min.fit(tbf_array, floc=0)
        
        # Validação básica
        if shape_c <= 0 or scale_lambda <= 0 or np.isnan(shape_c) or np.isnan(scale_lambda):
            raise ValueError("Parâmetros inválidos")
        
        # Teste de qualidade (Kolmogorov-Smirnov)
        quality = _assess_estimation_quality(tbf_array, shape_c, scale_lambda)
        
    except Exception:
        # Fallback: Método dos Momentos
        shape_c, scale_lambda = _estimate_weibull_method_of_moments(tbf_data)
        quality = "fallback"
    
    # Calcular MTBF e MTTR
    mtbf_estimated = scale_lambda * np.math.gamma(1 + 1/shape_c)
    mttr_mean = np.mean(ttr_data) if ttr_data else 1.0
    
    return {
        'tbf_shape': shape_c,
        'tbf_scale': scale_lambda,
        'mtbf_estimated': mtbf_estimated,
        'ttr_mean': mttr_mean,
        'sample_size': len(tbf_data),
        'estimation_quality': quality,
        'window_size_used': len(recent_failures)  # ✅ NOVO: Rastrear tamanho da janela
    }
    
    # ═══════════════════════════════════════════════════════════════
    # EXTRAIR TEMPOS ENTRE FALHAS (TBF)
    # ═══════════════════════════════════════════════════════════════
    tbf_data = []
    ttr_data = []
    
    sorted_history = sorted(failure_history, key=lambda f: f['failure_starts_at'])
    
    for i in range(len(sorted_history)):
        current_failure = sorted_history[i]
        
        # Tempo de reparo
        ttr = current_failure['becomes_available_at'] - current_failure['failure_starts_at']
        ttr_data.append(ttr)
        
        # Tempo entre falhas (TBF)
        if i > 0:
            previous_failure = sorted_history[i-1]
            tbf = current_failure['failure_starts_at'] - previous_failure['becomes_available_at']
            if tbf > 0:
                tbf_data.append(tbf)
    
    # ═══════════════════════════════════════════════════════════════
    # ESTIMAR PARÂMETROS WEIBULL PARA TBF
    # ═══════════════════════════════════════════════════════════════
    if len(tbf_data) < 2:
        return _default_weibull_params()
    
    tbf_array = np.array(tbf_data)
    
    try:
        # MLE (Maximum Likelihood Estimation)
        shape_c, loc, scale_lambda = stats.weibull_min.fit(tbf_array, floc=0)
        
        # Validação
        if shape_c <= 0 or scale_lambda <= 0 or not np.isfinite(shape_c) or not np.isfinite(scale_lambda):
            return _estimate_weibull_method_of_moments(tbf_data, ttr_data)
        
        # Estatísticas TTR
        ttr_mean = np.mean(ttr_data) if ttr_data else 50.0
        ttr_std = np.std(ttr_data) if len(ttr_data) > 1 else 20.0
        
        # Calcular MTBF estimado
        mtbf_estimated = scale_lambda * math.gamma(1 + 1/shape_c)
        
        # Avaliar qualidade
        quality = _assess_estimation_quality(tbf_data, shape_c, scale_lambda)
        
        return {
            'tbf_shape': shape_c,
            'tbf_scale': scale_lambda,
            'ttr_mean': ttr_mean,
            'ttr_std': ttr_std,
            'sample_size': len(tbf_data),
            'estimation_quality': quality,
            'mtbf_estimated': mtbf_estimated,
        }
        
    except Exception as e:
        return _estimate_weibull_method_of_moments(tbf_data, ttr_data)


def _default_weibull_params():
    """Retorna parâmetros padrão conservadores quando não há dados suficientes."""
    return {
        'tbf_shape': 1.0,
        'tbf_scale': 1000.0,
        'ttr_mean': 50.0,
        'ttr_std': 20.0,
        'sample_size': 0,
        'estimation_quality': 'insufficient',
        'mtbf_estimated': 1000.0,
    }


def _estimate_weibull_method_of_moments(tbf_data, ttr_data):
    """Método dos Momentos (fallback quando MLE falha)."""
    tbf_array = np.array(tbf_data)
    
    mean_tbf = np.mean(tbf_array)
    var_tbf = np.var(tbf_array)
    
    if var_tbf > 0:
        cv = sqrt(var_tbf) / mean_tbf
        shape_c = 1.0 / cv if cv > 0 else 1.0
    else:
        shape_c = 1.0
    
    scale_lambda = mean_tbf / math.gamma(1 + 1/shape_c)
    
    ttr_mean = np.mean(ttr_data) if ttr_data else 50.0
    ttr_std = np.std(ttr_data) if len(ttr_data) > 1 else 20.0
    
    return {
        'tbf_shape': shape_c,
        'tbf_scale': scale_lambda,
        'ttr_mean': ttr_mean,
        'ttr_std': ttr_std,
        'sample_size': len(tbf_data),
        'estimation_quality': 'poor',
        'mtbf_estimated': mean_tbf,
    }


def _assess_estimation_quality(tbf_data, shape_c, scale_lambda):
    """Avalia qualidade da estimação baseado em testes estatísticos."""
    n = len(tbf_data)
    
    if n < 3:
        return 'poor'
    elif n < 10:
        return 'fair'
    
    try:
        # Teste Kolmogorov-Smirnov
        ks_statistic, p_value = stats.kstest(tbf_data, 'weibull_min', args=(shape_c, 0, scale_lambda))
        
        if p_value > 0.10:
            return 'excellent'
        elif p_value > 0.05:
            return 'good'
        else:
            return 'fair'
    except:
        return 'fair'


# ============================================================================
# CONFIABILIDADE CONDICIONAL COM WEIBULL
# ============================================================================

def get_server_conditional_reliability_weibull(server, upcoming_instants):
    """
    Calcula confiabilidade condicional usando parâmetros Weibull estimados.
    
    R(t+Δt | t) = exp[-((t+Δt)/λ)^c + (t/λ)^c]
    """
    # 1. Estimar parâmetros do histórico (com cache)
    if not hasattr(server, 'model') or not server.model:
        current_step = 0
    else:
        current_step = server.model.schedule.steps
    
    params = get_cached_weibull_parameters(server, current_step)
    
    shape_c = params['tbf_shape']
    scale_lambda = params['tbf_scale']
    
    # 2. Calcular tempo desde último reparo
    time_since_repair = get_time_since_last_repair(server)
    
    # 3. Casos especiais
    if time_since_repair == float('inf'):
        time_since_repair = 0
    elif time_since_repair == 0:
        time_since_repair = 1
    else:
        time_since_repair = max(1, time_since_repair)
    
    # 4. Fórmula da Confiabilidade Condicional Weibull
    try:
        t = time_since_repair
        delta_t = upcoming_instants
        
        exponent1 = ((t + delta_t) / scale_lambda) ** shape_c
        exponent2 = (t / scale_lambda) ** shape_c
        
        conditional_reliability = math.exp(-(exponent1 - exponent2)) * 100
        return max(0.0, min(100.0, conditional_reliability))
        
    except (OverflowError, ZeroDivisionError):
        return 0.0


def get_server_conditional_reliability_weibull_with_confidence(server, upcoming_instants, confidence_level=0.95):
    """
    Calcula confiabilidade condicional COM intervalo de confiança baseado na qualidade da estimação.
    
    Ajustado para PEQUENAS AMOSTRAS usando decaimento suave (1/sqrt(n)).
    """
    params = get_cached_weibull_parameters(server, server.model.schedule.steps)
    
    shape_c = params['tbf_shape']
    scale_lambda = params['tbf_scale']
    sample_size = params['sample_size']
    
    time_since_repair = get_time_since_last_repair(server)
    
    # Proteções
    if time_since_repair == float('inf'):
        time_since_repair = 0
    elif time_since_repair == 0:
        time_since_repair = 1
    else:
        time_since_repair = max(1, time_since_repair)
    
    # Cálculo pontual da confiabilidade (Weibull)
    try:
        t = time_since_repair
        delta_t = upcoming_instants
        
        exponent1 = ((t + delta_t) / scale_lambda) ** shape_c
        exponent2 = (t / scale_lambda) ** shape_c
        
        reliability = math.exp(-(exponent1 - exponent2)) * 100.0
        reliability = max(0.0, min(100.0, reliability))
        
        # ---------------------------------------------------------------------
        # CÁLCULO DA INCERTEZA (MARGEM DE SEGURANÇA)
        # ---------------------------------------------------------------------
        # Problema anterior: Penalidade fixa de 40% para N < 3 gerava falsos positivos massivos.
        # Solução: Curva de decaimento baseada em 1/sqrt(N).
        #
        # Fórmula: Margem = Fator_Base / sqrt(N + 1)
        # Se N=0 -> Margem = 50% (Totalmente incerto)
        # Se N=1 -> Margem = 35%
        # Se N=3 -> Margem = 25%
        # Se N=10 -> Margem = 15%
        # Se N=100 -> Margem = 5%
        
        # Ajuste este fator: 0.50 significa que com 0 dados, a incerteza é +/- 50%
        BASE_UNCERTAINTY_FACTOR = 0.50 
        
        uncertainty_pct = (BASE_UNCERTAINTY_FACTOR / math.sqrt(sample_size + 1))
        
        # Penalidade extra se a qualidade do ajuste (KS-Test) for ruim
        quality = params.get('estimation_quality', 'fair')
        if quality == 'poor':
            uncertainty_pct *= 1.5  # Aumenta incerteza em 50% se o fit for ruim
        elif quality == 'excellent':
            uncertainty_pct *= 0.8  # Reduz se o fit for perfeito
            
        # Calcular limites
        # Lower Bound: É o valor que o TrustEdge usa para decidir migrar ("Pior cenário provável")
        lower_bound = max(0.0, reliability * (1.0 - uncertainty_pct))
        upper_bound = min(100.0, reliability * (1.0 + uncertainty_pct))
        
        # Opcional: Se a confiabilidade for EXTREMAMENTE alta (>99.9%),
        # a incerteza matemática importa menos. Clamp do limite inferior.
        if reliability > 99.9:
            lower_bound = max(lower_bound, 90.0) # Nunca rebaixe um 99.9% para menos de 90% só por incerteza
        
        return {
            'reliability': reliability,
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'uncertainty': (uncertainty_pct * 100),
            'confidence_level': confidence_level,
            'sample_size': sample_size
        }
        
    except (OverflowError, ZeroDivisionError):
        return {
            'reliability': 0.0,
            'lower_bound': 0.0,
            'upper_bound': 0.0,
            'uncertainty': 100.0,
            'confidence_level': confidence_level,
            'sample_size': 0
        }


def predict_next_n_failures(server, n_failures=3, max_horizon=200):
    """
    Prevê as próximas N falhas usando distribuição Weibull.
    """
    params = get_cached_weibull_parameters(server, server.model.schedule.steps)
    
    # ✅ DEBUG: Verificar qualidade da estimação
    if params.get('sample_size', 0) == 0:
        print(f"[PREDICT_FAILURES] ⚠️ Server {server.id}: SEM DADOS históricos (sample_size=0)")
        return []
    
    if params.get('estimation_quality') in ['insufficient', 'poor']:
        print(f"[PREDICT_FAILURES] ⚠️ Server {server.id}: Estimação {params['estimation_quality']} (sample={params['sample_size']})")
    
    shape_c = params['tbf_shape']
    scale_lambda = params['tbf_scale']
    ttr_mean = params['ttr_mean']
    
    current_step = server.model.schedule.steps + 1
    time_since_repair = get_time_since_last_repair(server)
    
    if time_since_repair == float('inf'):
        time_since_repair = 0
        print(f"[PREDICT_FAILURES] Server {server.id}: Nunca falhou ainda (time_since_repair=inf)")
    
    # ✅ LIMPEZA PERIÓDICA (adicionar AQUI)
    _cleanup_predict_failures_log_guard(current_step)
    
    log_key = (current_step, server.id, max_horizon)
    should_log = log_key not in _predict_failures_log_guard
    if should_log:
        _predict_failures_log_guard.add(log_key)

    predictions = []
    cumulative_time = time_since_repair
    failures_checked = 0
    failures_beyond_horizon = 0
    
    for i in range(1, n_failures + 1):
        try:
            expected_ttf = scale_lambda * math.gamma(1 + 1/shape_c)
        except (OverflowError, ValueError):
            expected_ttf = scale_lambda
        
        predicted_time = int(current_step + cumulative_time + expected_ttf)
        horizon = predicted_time - current_step
        
        # ✅ MUDANÇA: Não para, apenas registra e continua
        if horizon > max_horizon:
            failures_beyond_horizon += 1
            if should_log:
                print(f"[PREDICT_FAILURES] Server {server.id} - Failure {i}: {horizon} steps (além do horizonte)")
            cumulative_time += expected_ttf + ttr_mean
            continue

        failures_checked += 1
        
        # ✅ Se chegou aqui, está dentro do horizonte
        # Calcular probabilidade de falha
        try:
            # Usando CDF de Weibull
            probability = (1 - math.exp(-((cumulative_time + expected_ttf) / scale_lambda) ** shape_c)) * 100
        except (OverflowError, ValueError):
            probability = 50.0
        
        # Calcular downtime esperado
        expected_downtime = ttr_mean
        
        predictions.append({
            'horizon': horizon,
            'predicted_step': predicted_time,
            'probability': min(100.0, probability),
            'expected_downtime': expected_downtime,
            'failure_sequence': i
        })
        
        print(f"                   ✅ DENTRO do horizonte - Prob: {probability:.1f}%")
        
        # Atualizar tempo acumulado (TTF + TTR)
        cumulative_time += expected_ttf + ttr_mean
    
        if should_log:
            print(f"                   ✅ DENTRO do horizonte - Prob: {probability:.1f}%")

    if should_log:
        print(f"[PREDICT_FAILURES] Server {server.id} - Resumo:")
        print(f"                   Falhas verificadas: {failures_checked}")
        print(f"                   Além do horizonte: {failures_beyond_horizon}")
        print(f"                   Dentro do horizonte: {len(predictions)}")

    return predictions

# ============================================================================
# CACHE DE ESTIMAÇÕES (Otimização de Performance)
# ============================================================================

_weibull_estimation_cache = {}

def get_cached_weibull_parameters(server, current_step, cache_validity=50):
    """
    Retorna parâmetros Weibull com cache (reestima a cada N steps).
    """
    server_id = server.id
    
    window_size = getattr(server.model, '_trust_edge_window_size', 10)
    
    if server_id in _weibull_estimation_cache:
        cached = _weibull_estimation_cache[server_id]
        if current_step - cached['updated_at'] < cache_validity:
            return cached['params']
    
    params = estimate_weibull_parameters_from_history(server, window_size=window_size)
    
    _weibull_estimation_cache[server_id] = {
        'params': params,
        'updated_at': current_step
    }
    
    return params


def reset_weibull_estimation_cache():
    """Limpa cache de estimações (útil entre simulações)."""
    global _weibull_estimation_cache
    _weibull_estimation_cache = {}


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

def get_application_delay_cost(app: object) -> float:
    """
    Calcula score de prioridade baseado na ESCASSEZ de servidores viáveis.
    
    Lógica:
    1. Conta quantos servidores disponíveis (status='available') atendem ao SLA de delay da aplicação.
    2. O score é inversamente proporcional a essa contagem.
       - Menos opções = Maior Score (Maior Prioridade).
    
    Exemplo:
    - App A (SLA 20): 5 servidores atendem -> Score = 1/5 = 0.2
    - App B (SLA 30): 1 servidor atende   -> Score = 1/1 = 1.0 (Prioridade 5x maior)
    """
    user = app.users[0]
    delay_sla = user.delay_slas[str(app.id)]
    
    # Identificar componentes de rede
    user_switch = user.base_station.network_switch
    wireless_delay = user.base_station.wireless_delay
    
    # Filtrar apenas servidores funcionais
    available_servers = [s for s in EdgeServer.all() if s.status == "available"]
    
    viable_servers_count = 0
    
    for edge_server in available_servers:
        # Calcular delay total usando a topologia
        total_delay = get_delay(
            wireless_delay=wireless_delay,
            origin_switch=user_switch,
            target_switch=edge_server.network_switch
        )
        
        # Verificar se este servidor atende ao SLA
        if total_delay <= delay_sla:
            viable_servers_count += 1
    
    # Calcular Score de Escassez
    if viable_servers_count == 0:
        # Caso Crítico: Nenhuma opção viável.
        # Retorna um valor alto para tentar alocar no "menos pior" com prioridade máxima.
        return 100.0 
    else:
        # Inversamente proporcional ao número de opções
        return 1.0 / viable_servers_count

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
        user_access_patterns = user.access_patterns[str(service.application.id)]
        service_expected_duration = user_access_patterns.duration_values[0]
        power_consumption = edge_server.power_model_parameters["max_power_consumption"]
        
        # ✅ NOVO: Calcular tempo REAL de provisionamento
        provisioning_estimate = estimate_provisioning_time_for_server(
            target_server=edge_server,
            service=service,
            verbose=False
        )
        
        # Confiabilidade usando Weibull
        weibull_data = get_server_conditional_reliability_weibull_with_confidence(
            server=edge_server, 
            upcoming_instants=service_expected_duration
        )
        
        real_weibull_reliability = weibull_data['reliability']
        
        # Recalcular trust_cost baseado no Weibull.
        # Se confiabilidade = 100% (1.0), Custo = 0.0
        # Se confiabilidade = 0% (0.0), Custo = 1.0
        trust_cost = 1.0 - (real_weibull_reliability / 100.0)
        
        # ✅ SUBSTITUIR: amount_of_uncached_layers POR métricas reais
        service_image = ContainerImage.find_by(attribute_name="digest", attribute_value=service.image_digest)
        service_layers = [ContainerLayer.find_by(attribute_name="digest", attribute_value=digest) 
                         for digest in service_image.layers_digests]
        
        uncached_layers = [layer for layer in service_layers 
                          if not any(cached.digest == layer.digest for cached in edge_server.container_layers)]
        
        # ✅ NOVAS MÉTRICAS:
        amount_of_uncached_layers = len(uncached_layers)  # Contagem (compatibilidade)
        total_uncached_mb = sum(layer.size for layer in uncached_layers)  # TAMANHO TOTAL
        estimated_provisioning_time = provisioning_estimate['total_time_steps']  # TEMPO ESTIMADO
        
        host_candidates.append({
            "object": edge_server,
            "overall_delay": path_delay,
            "sla_violations": sla_violations,
            "free_capacity": get_normalized_free_capacity(edge_server),
            "trust_cost": trust_cost,
            "power_consumption": power_consumption,
            "reliability_value": real_weibull_reliability,
            
            # ✅ Métricas antigas (manter compatibilidade)
            "amount_of_uncached_layers": amount_of_uncached_layers,
            
            # ✅ NOVAS MÉTRICAS DE DOWNLOAD
            "total_uncached_mb": total_uncached_mb,
            "estimated_provisioning_time": estimated_provisioning_time,
            "download_queue_size": len(edge_server.download_queue),
            "provisioning_bottleneck": provisioning_estimate['bottleneck'],
        })
    
    return host_candidates

# ✅ CACHE GLOBAL de camadas por digest
_LAYER_CACHE = {}

def _get_layer_by_digest(digest):
    """
    Retorna camada usando cache.
    Cache construído no primeiro acesso e persiste durante simulação.
    """
    global _LAYER_CACHE
    
    # Construir cache na primeira vez
    if not _LAYER_CACHE:
        for layer in ContainerLayer.all():
            _LAYER_CACHE[layer.digest] = layer
        print(f"[LAYER_CACHE] Índice construído: {len(_LAYER_CACHE)} camadas")
    
    return _LAYER_CACHE.get(digest)

def estimate_migration_time_in_steps(target_server, service, bandwidth_mbps=100.0):
    """
    Estima quantos steps o Live Migration levará com base no tamanho das camadas não cacheadas.
    Considera largura de banda da rede (padrão 100Mbps ~ 12.5 MB/s).
    
    ✅ COM CACHE (Opcional).
    """
    global _provisioning_time_cache
    
    # ✅ CORREÇÃO 1: Validar que target_server tem model
    if not hasattr(target_server, 'model') or target_server.model is None:
        return {'total_time_steps': float('inf'), 'bottleneck': 'no_model'}
    
    # ✅ CORREÇÃO 2: Definir cache_key LOGO NO INÍCIO
    current_step = target_server.model.schedule.steps + 1
    cache_key = (target_server.id, service.image_digest, current_step, 'migration')
    
    # ✅ Verificar cache
    if cache_key in _provisioning_time_cache:
        return _provisioning_time_cache[cache_key]
    
    # ═══════════════════════════════════════════════════════════
    # CÁLCULO NORMAL
    # ═══════════════════════════════════════════════════════════
    
    BANDWIDTH_MB_PER_SEC = bandwidth_mbps / 8.0
    
    # 1. Identificar imagem e camadas
    service_image = ContainerImage.find_by(attribute_name="digest", attribute_value=service.image_digest)
    if not service_image:
        result = {'total_time_steps': float('inf'), 'bottleneck': 'no_image'}
        _provisioning_time_cache[cache_key] = result  # ✅ AGORA É SEGURO
        return result
    
    # ✅ OTIMIZAÇÃO: Usar cache de layers
    service_layers = [_get_layer_by_digest(digest) 
                     for digest in service_image.layers_digests]
    service_layers = [l for l in service_layers if l is not None]
    
    # 2. Calcular tamanho total a baixar
    total_size_mb = 0
    for layer in service_layers:
        is_cached = any(cached.digest == layer.digest for cached in target_server.container_layers)
        if not is_cached:
            total_size_mb += layer.size
            
    # 3. Converter para steps
    if total_size_mb == 0:
        result = {'total_time_steps': 2, 'bottleneck': 'cache'}
        _provisioning_time_cache[cache_key] = result
        return result
        
    estimated_steps = int(math.ceil(total_size_mb / BANDWIDTH_MB_PER_SEC)) + 2
    
    result = {
        'total_time_steps': estimated_steps,
        'total_mb_to_download': total_size_mb,
        'bottleneck': 'bandwidth' if estimated_steps > 10 else 'none'
    }
    
    # ✅ Armazenar no cache
    _provisioning_time_cache[cache_key] = result
    
    return result


_provisioning_time_cache = {}

def _cleanup_provisioning_time_cache(current_step):
    """
    Remove entradas de steps antigos do cache de estimações.
    Executado periodicamente para evitar crescimento de memória.
    """
    global _provisioning_time_cache
    
    if current_step % 10 == 0:  # Limpar a cada 10 steps
        cutoff = current_step - 2  # Manter apenas últimos 2 steps
        keys_to_remove = [k for k in _provisioning_time_cache.keys() if k[2] < cutoff]
        
        for key in keys_to_remove:
            del _provisioning_time_cache[key]
        
        if keys_to_remove:
            print(f"[CACHE_CLEANUP] {len(keys_to_remove)} estimações antigas removidas (total: {len(_provisioning_time_cache)})")
            
def estimate_provisioning_time_for_server(target_server, service, verbose=False):
    """
    Estima tempo total (em steps) para provisionar serviço em um servidor.
    
    ✅ OTIMIZAÇÃO: Cache por (servidor, imagem, step).
    Invalida automaticamente a cada step (queue_size muda).
    """
    global _provisioning_time_cache
    
    # ✅ VALIDAÇÃO INICIAL: Garantir que server.model existe
    if not hasattr(target_server, 'model') or target_server.model is None:
        print(f"[ESTIMATE_PROVISIONING] ⚠️ ERRO: target_server {target_server.id} sem model")
        return {
            'total_time_steps': float('inf'),
            'total_mb_to_download': 0,
            'layers_to_download': 0,
            'download_sources': {},
            'bottleneck': 'no_model',
        }
    
    # ✅ CORREÇÃO: Definir cache_key LOGO NO INÍCIO (antes de qualquer uso)
    current_step = target_server.model.schedule.steps + 1
    cache_key = (target_server.id, service.image_digest, current_step)
    
    # ✅ Verificar cache (AGORA cache_key já existe)
    if cache_key in _provisioning_time_cache:
        return _provisioning_time_cache[cache_key]
    
    # ═══════════════════════════════════════════════════════════
    # CÁLCULO NORMAL
    # ═══════════════════════════════════════════════════════════
    
    from simulator.extensions.edge_server_extensions import get_layer_download_config
    config = get_layer_download_config()
    
    if not config["enable_registry"] and not config["enable_p2p"]:
        result = {
            'total_time_steps': float('inf'),
            'total_mb_to_download': 0,
            'layers_to_download': 0,
            'download_sources': {},
            'bottleneck': 'no_download_sources',
        }
        _provisioning_time_cache[cache_key] = result  # ✅ AGORA É SEGURO
        return result
    
    service_image = ContainerImage.find_by(attribute_name="digest", attribute_value=service.image_digest)
    if not service_image:
        result = {'total_time_steps': float('inf'), 'bottleneck': 'no_image'}
        _provisioning_time_cache[cache_key] = result  # ✅ AGORA É SEGURO
        return result
    
    # ✅ OTIMIZAÇÃO: Usar cache de layers
    service_layers = [_get_layer_by_digest(digest) 
                     for digest in service_image.layers_digests]
    service_layers = [l for l in service_layers if l is not None]  # Filtrar None
    
    cached_layers = [layer for layer in service_layers 
                     if any(cached.digest == layer.digest for cached in target_server.container_layers)]
    
    uncached_layers = [layer for layer in service_layers 
                       if layer not in cached_layers]
    
    if not uncached_layers:
        result = {
            'total_time_steps': 0,
            'total_mb_to_download': 0,
            'layers_to_download': 0,
            'download_sources': {},
            'bottleneck': 'cache'
        }
        _provisioning_time_cache[cache_key] = result
        return result
    
    # ✅ OTIMIZAÇÃO: Pré-filtrar fontes disponíveis UMA VEZ
    available_registries = []
    available_p2p_servers = []
    
    if config["enable_registry"]:
        available_registries = [
            reg.server for reg in ContainerRegistry.all() 
            if reg.available and reg.server
        ]
    
    if config["enable_p2p"]:
        available_p2p_servers = [
            s for s in EdgeServer.all() 
            if s.available and s.id != target_server.id
        ]
    
    # Processar camadas
    download_plan = {}
    total_mb_to_download = 0
    has_missing_layers = False
    missing_layers_details = []
    
    for layer in uncached_layers:
        sources = []
        
        # ✅ OTIMIZAÇÃO: Usar listas pré-filtradas
        for server in available_registries:
            if any(l.digest == layer.digest for l in server.container_layers):
                sources.append(('registry', server))
        
        for server in available_p2p_servers:
            if any(l.digest == layer.digest for l in server.container_layers):
                sources.append(('p2p', server))
        
        if not sources:
            has_missing_layers = True
            missing_layers_details.append(layer.digest[:12])
            
            download_plan[layer.digest] = {
                'type': 'missing',
                'server': None,
                'download_time': float('inf')
            }
            continue
        
        # Avaliar fontes
        best_source = None
        best_download_time = float('inf')
        
        for source_type, source_server in sources:
            download_time = _estimate_download_time_from_source(
                layer=layer,
                source_server=source_server,
                target_server=target_server,
                source_type=source_type
            )
            
            if download_time < best_download_time:
                best_download_time = download_time
                best_source = {
                    'type': source_type,
                    'server': source_server,
                    'download_time': download_time
                }
        
        download_plan[layer.digest] = best_source
        total_mb_to_download += layer.size
    
    if has_missing_layers:
        result = {
            'total_time_steps': float('inf'),
            'total_mb_to_download': total_mb_to_download,
            'layers_to_download': len(uncached_layers),
            'download_sources': download_plan,
            'bottleneck': 'missing_layers',
            'missing_layers': missing_layers_details,
        }
        _provisioning_time_cache[cache_key] = result
        return result
    
    max_concurrent = target_server.max_concurrent_layer_downloads
    current_queue_size = len(target_server.download_queue)
    
    if current_queue_size >= max_concurrent:
        avg_remaining_time = _estimate_avg_remaining_download_time(target_server)
        queue_delay = avg_remaining_time
    else:
        queue_delay = 0
    
    individual_times = [info['download_time'] for info in download_plan.values() if info['download_time'] != float('inf')]
    
    if not individual_times:
        parallel_download_time = float('inf')
    else:
        parallel_download_time = max(individual_times)
    
    total_time = queue_delay + parallel_download_time
    
    if queue_delay > parallel_download_time:
        bottleneck = 'download_queue'
    elif parallel_download_time > 10:
        bottleneck = 'bandwidth'
    else:
        bottleneck = 'none'
    
    if verbose:
        print(f"[ESTIMATE_PROVISIONING] Servidor {target_server.id}:")
        print(f"  Camadas cacheadas: {len(cached_layers)}/{len(service_layers)}")
        print(f"  Camadas para baixar: {len(uncached_layers)} ({total_mb_to_download:.2f} MB)")
        print(f"  Fila de download: {current_queue_size}/{max_concurrent}")
        print(f"  Tempo de espera na fila: {queue_delay} steps")
        print(f"  Tempo de download paralelo: {parallel_download_time} steps")
        print(f"  TOTAL: {total_time} steps")
    
    result = {
        'total_time_steps': int(total_time) if total_time != float('inf') else float('inf'),
        'total_mb_to_download': total_mb_to_download,
        'layers_to_download': len(uncached_layers),
        'download_sources': download_plan,
        'bottleneck': bottleneck,
        'queue_delay': queue_delay,
        'parallel_download_time': parallel_download_time
    }
    
    # ✅ Armazenar no cache
    _provisioning_time_cache[cache_key] = result
    
    return result




# ✅ CACHE GLOBAL de métricas de caminho
_PATH_METRICS_CACHE = {}  # {(source_switch_id, target_switch_id): {'bandwidth': X, 'delay': Y}}

def _get_path_metrics(source_switch, target_switch, topology):
    """
    ✅ OTIMIZAÇÃO: Cache de métricas de caminho (bandwidth + delay).
    Cache permanente durante simulação (topologia não muda).
    """
    global _PATH_METRICS_CACHE
    
    cache_key = (source_switch.id, target_switch.id)
    
    if cache_key in _PATH_METRICS_CACHE:
        return _PATH_METRICS_CACHE[cache_key]
    
    # Calcular caminho
    try:
        path = nx.shortest_path(
            G=topology,
            source=source_switch,
            target=target_switch,
        )
    except nx.NetworkXNoPath:
        result = {'bandwidth': 0, 'delay': float('inf'), 'path': []}
        _PATH_METRICS_CACHE[cache_key] = result
        return result
    
    # Calcular métricas
    min_bandwidth = float('inf')
    total_delay = 0
    
    for i in range(len(path) - 1):
        link_data = topology[path[i]][path[i + 1]]
        link_bandwidth = link_data.get('bandwidth', 100)
        link_delay = link_data.get('delay', 0)
        
        min_bandwidth = min(min_bandwidth, link_bandwidth)
        total_delay += link_delay
    
    result = {
        'bandwidth': min_bandwidth,
        'delay': total_delay,
        'path': path
    }
    
    _PATH_METRICS_CACHE[cache_key] = result
    return result


def _estimate_download_time_from_source(layer, source_server, target_server, source_type):
    """
    ✅ OTIMIZAÇÃO: Usa cache de métricas de caminho.
    """
    topology = target_server.model.topology
    source_switch = source_server.base_station.network_switch
    target_switch = target_server.base_station.network_switch
    
    # ✅ Obter métricas do cache
    path_metrics = _get_path_metrics(source_switch, target_switch, topology)
    
    if path_metrics['bandwidth'] == 0:
        return float('inf')  # Sem caminho
    
    min_bandwidth = path_metrics['bandwidth']
    total_delay = path_metrics['delay']
    
    # 3. Ajustar por downloads ativos
    active_downloads_from_source = sum(
        1 for flow in topology.graph.get('flows', [])
        if hasattr(flow, 'source') and flow.source == source_server and flow.status == 'active'
    )
    
    effective_bandwidth = min_bandwidth / max(1, active_downloads_from_source)
    
    # 4. Calcular tempo de download
    bandwidth_mb_per_sec = effective_bandwidth / 8.0
    download_time_seconds = layer.size / bandwidth_mb_per_sec
    download_time_steps = int(download_time_seconds) + 1
    
    total_time = download_time_steps + total_delay
    
    return total_time


def _estimate_avg_remaining_download_time(server):
    """
    Estima tempo médio restante dos downloads ativos no servidor.
    """
    if not server.download_queue:
        return 0
    
    # Simplificação: assumir que downloads restantes levam 50% do tempo médio
    avg_layer_size = 50  # MB (estimativa)
    avg_bandwidth = 100 / 8  # MB/s (100 Mbps)
    avg_time_per_download = avg_layer_size / avg_bandwidth
    
    # Tempo médio = metade do tempo de um download (já parcialmente concluído)
    return int(avg_time_per_download / 2)

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


def collect_all_sla_violations():
    """
    Coleta todas as violações de SLA consolidadas.
    Retorna um dicionário com métricas agregadas.
    """
    metrics = get_simulation_metrics()
    consolidated = metrics.get_consolidated_metrics()
    
    # Calcular delay médio
    total_delays = 0
    delay_count = 0
    
    for user in User.all():
        for app in user.applications:
            app_id = str(app.id)
            if app_id in user.delays:
                delay = user.delays[app_id]
                if delay != float('inf') and delay > 0:
                    total_delays += delay
                    delay_count += 1
    
    avg_delay = total_delays / delay_count if delay_count > 0 else 0
    
    return {
        "total_delay_sla_violations": consolidated.get("total_delay_sla_violations", 0),
        "delay_violations_per_delay_sla": consolidated.get("delay_violations_per_delay_sla", {}),
        "delay_violations_per_access_pattern": consolidated.get("delay_violations_per_access_pattern", {}),
        "total_perceived_downtime": consolidated.get("total_perceived_downtime", 0),
        "total_perceived_downtime_per_access_pattern": consolidated.get("total_perceived_downtime_per_access_pattern", {}),
        "total_perceived_downtime_per_delay_sla": consolidated.get("total_perceived_downtime_per_delay_sla", {}),
        "total_downtime_sla_violations": consolidated.get("total_downtime_sla_violations", 0),
        "apps_violations_sla_downtime": consolidated.get("apps_violations_sla_downtime", []),
        "downtime_violations_per_access_pattern": consolidated.get("downtime_violations_per_access_pattern", {}),
        "downtime_violations_per_delay_sla": consolidated.get("downtime_violations_per_delay_sla", {}),
        "total_simulation_steps": consolidated.get("total_simulation_steps", 0),
        "average_delay": avg_delay,
    }


def collect_all_infrastructure_metrics():
    """
    Coleta todas as métricas de infraestrutura consolidadas.
    Retorna um dicionário com métricas agregadas.
    """
    metrics = get_simulation_metrics()
    consolidated = metrics.get_consolidated_metrics()
    
    return {
        "total_servers_per_model": consolidated.get("total_servers_per_model", {}),
        "total_overloaded_servers": consolidated.get("total_overloaded_servers", 0),
        "average_overall_occupation": consolidated.get("average_overall_occupation", 0),
        "average_occupation_per_model": consolidated.get("average_occupation_per_model", {}),
        "average_available_overall_occupation": consolidated.get("average_available_overall_occupation", 0),
        "average_available_occupation_per_model": consolidated.get("average_available_occupation_per_model", {}),
        "total_power_consumption": consolidated.get("total_power_consumption", 0),
        "total_power_consumption_per_model": consolidated.get("total_power_consumption_per_model", {}),
    }


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


# ============================================================================
# ✅ CENTRALIZAÇÃO: RASTREAMENTO DE DISPONIBILIDADE E DELAYS
# ============================================================================

def is_service_available_for_user(service, user, application, current_step):
    """
    Determina se um serviço está REALMENTE disponível para o usuário.
    
    Retorna:
        (bool, str): (disponível?, razão_da_indisponibilidade)
    
    Razões possíveis:
        - None: Disponível
        - "user_not_accessing": Usuário não está acessando
        - "no_server_allocated": Serviço sem servidor
        - "server_unavailable": Servidor indisponível
        - "migration_in_progress": Migração ativa (ÚNICA razão de migração)
        - "service_not_available": Serviço marcado como indisponível
    """
    # Regra 1: Usuário deve estar acessando
    if not is_user_accessing_application(user, application, current_step):
        return (False, "user_not_accessing")
    
    # Regra 2: Serviço deve ter servidor
    if not service.server:
        return (False, "no_server_allocated")
    
    # Regra 3: Servidor deve estar disponível
    if not service.server.available or service.server.status != "available":
        return (False, "server_unavailable")
    
    # ✅ REGRA 4: Verificar migração ativa (ANTES de checar service._available)
    if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
        last_migration = service._Service__migrations[-1]
        
        if last_migration.get("end") is None:  # Migração ativa
            from simulator.extensions.service_extensions import get_migration_config
            config = get_migration_config()
            
            # ✅ LIVE MIGRATION: Serviço pode estar disponível na origem
            if config["enable_live_migration"]:
                origin = last_migration.get("origin")
                
                # Verificar se serviço ESTÁ na origem E origem disponível
                if origin and service.server == origin and origin.available:
                    # ✅ Disponível durante Live Migration
                    return (True, "available_on_origin")
            
            # ✅ COLD MIGRATION ou CUTOVER: Sempre indisponível durante migração ativa
            # Retornar SEMPRE "migration_in_progress" (única razão)
            # A classificação detalhada (cold/hot, waiting/downloading) será feita em _classify_downtime_cause_v2()
            return (False, "migration_in_progress")
    
    # Regra 5: Serviço deve estar marcado como disponível
    if not service._available:
        return (False, "service_not_available")
    
    # ✅ Todas as verificações passaram
    return (True, None)


def calculate_user_delay_for_application(user, application, current_step):
    """
    Calcula o delay REAL percebido pelo usuário para uma aplicação.
    
    REGRAS:
    1. Se usuário NÃO está acessando: delay = 0 (não conta)
    2. Se serviço INDISPONÍVEL: delay = inf (violação crítica)
    3. Se serviço DISPONÍVEL: calcular delay de rede normal
    
    Returns:
        tuple: (delay: float, unavailability_reason: str or None)
    """
    service = application.services[0]
    
    # Regra 1: Usuário não está acessando
    if not is_user_accessing_application(user, application, current_step):
        return (0, None)
    
    # Regra 2: Verificar disponibilidade
    is_available, unavailability_reason = is_service_available_for_user(
        service, user, application, current_step
    )
    
    if not is_available:
        return (float('inf'), unavailability_reason)
    
    # Regra 3: Serviço disponível - calcular delay normal
    user.set_communication_path(app=application)
    delay = user._compute_delay(app=application, metric="latency")
    
    return (delay, None)


def update_all_user_delays(current_step):
    """
    Atualiza delays de TODOS os usuários de forma centralizada e consistente.
    
    Esta função DEVE SER CHAMADA por TODOS os algoritmos para garantir consistência.
    """
    for user in User.all():
        for app in user.applications:
            app_id = str(app.id)
            
            delay, unavailability_reason = calculate_user_delay_for_application(
                user, app, current_step
            )
            
            user.delays[app_id] = delay
            
            # ✅ DEBUG (opcional - pode ser removido em produção)
            if current_step % 50 == 0 and delay != 0:
                service = app.services[0]
                server_info = f"Server {service.server.id}" if service.server else "No Server"
                
                if delay == float('inf'):
                    print(f"[DELAY_UPDATE] User {user.id} | App {app.id}: INDISPONÍVEL ({unavailability_reason}) | {server_info}")
                else:
                    print(f"[DELAY_UPDATE] User {user.id} | App {app.id}: {delay:.2f} | {server_info}")


# ============================================================================
# ✅ CENTRALIZAÇÃO: CONTABILIZAÇÃO DE SLA VIOLATIONS (CORRIGIDA)
# ============================================================================

def collect_sla_violations_for_current_step():
    """
    Coleta violações de SLA de delay de forma CENTRALIZADA e CONSISTENTE.
    
    REGRAS CORRIGIDAS:
    1. Se delay = inf (serviço indisponível): SEMPRE viola SLA
    2. Se delay > delay_sla: viola SLA
    3. Se delay ≤ delay_sla: NÃO viola
    4. Se usuário NÃO está acessando (delay=0): NÃO conta
    """
    from simulator.helper_functions import get_simulation_metrics
    
    current_step = Topology.first().model.schedule.steps + 1
    metrics = get_simulation_metrics()
    
    total_violations_this_step = 0
    
    for user in User.all():
        for app in user.applications:
            app_id = str(app.id)
            
            # ✅ REGRA 4: Pular se usuário não está acessando
            if not is_user_accessing_application(user, app, current_step):
                continue
            
            delay_sla = user.delay_slas.get(app_id)
            current_delay = user.delays.get(app_id, 0)
            
            # ✅ OBTER ACCESS PATTERN (para contabilização correta)
            access_pattern = user.access_patterns[app_id]
            duration = access_pattern.duration_values[0] if access_pattern.duration_values else 0
            
            # ✅ REGRA 1: delay = inf SEMPRE viola
            if current_delay == float('inf'):
                total_violations_this_step += 1
                
                # Contabilizar por aplicação
                if app_id not in metrics.delay_violations_per_application:
                    metrics.delay_violations_per_application[app_id] = 0
                metrics.delay_violations_per_application[app_id] += 1
                
                # Contabilizar por SLA
                sla_key = str(delay_sla)
                if sla_key not in metrics.delay_violations_per_delay_sla:
                    metrics.delay_violations_per_delay_sla[sla_key] = 0
                metrics.delay_violations_per_delay_sla[sla_key] += 1
                
                # ✅ CORREÇÃO: Contabilizar por access pattern
                if duration not in metrics.delay_violations_per_access_pattern:
                    metrics.delay_violations_per_access_pattern[duration] = 0
                metrics.delay_violations_per_access_pattern[duration] += 1
                
                continue
            
            # ✅ REGRA 2: delay > sla viola
            if current_delay > delay_sla:
                total_violations_this_step += 1
                
                # Contabilizar por aplicação
                if app_id not in metrics.delay_violations_per_application:
                    metrics.delay_violations_per_application[app_id] = 0
                metrics.delay_violations_per_application[app_id] += 1
                
                # Contabilizar por SLA
                sla_key = str(delay_sla)
                if sla_key not in metrics.delay_violations_per_delay_sla:
                    metrics.delay_violations_per_delay_sla[sla_key] = 0
                metrics.delay_violations_per_delay_sla[sla_key] += 1
                
                # ✅ CORREÇÃO: Contabilizar por access pattern
                if duration not in metrics.delay_violations_per_access_pattern:
                    metrics.delay_violations_per_access_pattern[duration] = 0
                metrics.delay_violations_per_access_pattern[duration] += 1
    
    # ✅ Armazenar total
    metrics.total_delay_sla_violations += total_violations_this_step
    
    # ✅ Log periódico
    if current_step % 100 == 0:
        print(f"[SLA_VIOLATIONS] Step {current_step}: {total_violations_this_step} violações neste step")
        print(f"                 Total acumulado: {metrics.total_delay_sla_violations}")


# ============================================================================
# ✅ CENTRALIZAÇÃO: RASTREAMENTO DE DOWNTIME (CORRIGIDO)
# ============================================================================

def update_user_perceived_downtime_for_current_step(current_step):
    """
    Atualiza downtime percebido de forma CENTRALIZADA e CONSISTENTE.
    
    REGRAS CORRIGIDAS:
    1. Downtime SOMENTE quando delay = inf E usuário está acessando
    2. Classificar causa usando is_service_available_for_user()
    3. Contabilizar por usuário e globalmente
    """
    
    metrics = get_simulation_metrics()
    total_downtime_this_step = 0
    
    print(f"\n{'='*70}")
    print(f"[DEBUG_DOWNTIME] === MONITORANDO O DOWNTIME PERCEBIDO - STEP {current_step} ===")
    print(f"{'='*70}")
    
    for user in User.all():
        if not hasattr(user, '_perceived_downtime'):
            user._perceived_downtime = {}
        
        # ✅ CORREÇÃO: Inicializar user_perceived_downtime_history
        if not hasattr(user, 'user_perceived_downtime_history'):
            user.user_perceived_downtime_history = {}
        
        for app in user.applications:
            app_id = str(app.id)
            service = app.services[0]
            
            # ✅ Inicializar histórico para este app (se não existir)
            if app_id not in user.user_perceived_downtime_history:
                user.user_perceived_downtime_history[app_id] = []
            
            # ✅ REGRA: Só conta downtime se usuário ESTÁ acessando
            if not is_user_accessing_application(user, app, current_step):
                # ✅ CORREÇÃO: Adicionar False ao histórico mesmo quando não está acessando
                user.user_perceived_downtime_history[app_id].append(False)
                continue
            
            # ✅ Verificar disponibilidade
            is_available, unavailability_reason = is_service_available_for_user(
                service, user, app, current_step
            )
            
            # ✅ CORREÇÃO: Adicionar ao histórico (True = downtime, False = disponível)
            user.user_perceived_downtime_history[app_id].append(not is_available)
            
            if not is_available:
                # ✅ DOWNTIME DETECTADO
                total_downtime_this_step += 1
                
                # Contabilizar por usuário (para compatibilidade)
                if app_id not in user._perceived_downtime:
                    user._perceived_downtime[app_id] = 0
                user._perceived_downtime[app_id] += 1
                
                # ✅ Classificar causa DETALHADA
                detailed_cause = _classify_downtime_cause_v2(
                    user, app, service, current_step, unavailability_reason
                )
                
                # Contabilizar globalmente por causa
                if detailed_cause not in metrics.downtime_reasons:
                    metrics.downtime_reasons[detailed_cause] = 0
                metrics.downtime_reasons[detailed_cause] += 1
                
                # ✅ LOG (só primeiras ocorrências para não poluir)
                if metrics.downtime_reasons[detailed_cause] <= 3:
                    server_info = f"{service.server.id} (disponível: {service.server.available})" if service.server else "None"
                    
                    print(f"[DEBUG_DOWNTIME] User {user.id} | App {app.id} | Service {service.id}")
                    print(f"                 Causa: {detailed_cause}")
                    print(f"                 Delay atual: {user.delays.get(app_id, 0)}")
                    print(f"                 Status serviço: available={service._available}")
                    print(f"                 Servidor: {server_info}")
    
    # ✅ Atualizar total global
    metrics.total_perceived_downtime += total_downtime_this_step
    
    print(f"{'='*70}\n")
    
    # ✅ Log periódico
    if current_step % 100 == 0:
        print(f"[DOWNTIME_SUMMARY] Step {current_step}: {total_downtime_this_step} steps de downtime neste step")
        print(f"                   Total acumulado: {metrics.total_perceived_downtime}")


_unclassified_cases = []

def _classify_downtime_cause_v2(user, app, service, current_step, unavailability_reason):
    """
    Classifica a causa do downtime de forma DETALHADA e CONSISTENTE.
    """
    global _unclassified_cases
    
    # ✅ CASO 0: Serviço disponível (não é downtime)
    if unavailability_reason in [None, "available_on_origin"]:
        return None
    
    # ✅ CASO 1: Sem servidor alocado
    if unavailability_reason == "no_server_allocated":
        from simulator.algorithms.trust_edge_v3 import is_application_in_waiting_queue
        
        if is_application_in_waiting_queue(app.id):
            return "waiting_queue_global"
        
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            return "provisioning_initial"
        
        return "server_failure_orphaned"
    
    # ✅ CASO 2: Servidor indisponível
    if unavailability_reason == "server_unavailable":
        return "server_failure_unavailable"
    
    # ✅ CASO 3: Migração em andamento (detectada explicitamente)
    if unavailability_reason == "migration_in_progress":
        if not hasattr(service, '_Service__migrations') or len(service._Service__migrations) == 0:
            print(f"[CLASSIFY_DOWNTIME] ⚠️ BUG: 'migration_in_progress' mas sem migrações! Service {service.id}")
            return "downtime_unclassified"
        
        migration = service._Service__migrations[-1]
        origin = migration.get("origin")
        status = migration.get("status", "unknown")
        
        # ✅ VALIDAÇÃO: Migração deve estar ativa (end=None)
        if migration.get("end") is not None:
            print(f"[CLASSIFY_DOWNTIME] ⚠️ Migração FINALIZADA mas serviço indisponível!")
            print(f"                    Service {service.id}, Status: {status}, End: {migration.get('end')}")
            
            if status == "interrupted":
                return "server_failure_orphaned"
            
            if status == "finished":
                return "service_startup_delay"
            
            return "migration_completed_but_unavailable"
        
        # ✅ Determinar se é provisionamento (origin=None) ou migração
        is_provisioning = (origin is None)
        
        # ✅ Obter configuração de Live Migration
        from simulator.extensions.service_extensions import get_migration_config
        config = get_migration_config()
        is_live_migration_enabled = config.get("enable_live_migration", True)
        
        # Obter razão original da migração
        original_reason = migration.get("original_migration_reason", "unknown")
        
        # ✅ VALIDAÇÃO: original_reason NÃO pode ser "unknown"
        if original_reason == "unknown" or not original_reason:
            print(f"[CLASSIFY_DOWNTIME] ⚠️ original_migration_reason = '{original_reason}' (Service {service.id})")
            print(f"                    migration_reason: {migration.get('migration_reason')}")
            print(f"                    status: {status}, origin: {origin.id if origin else 'None'}")
            
            migration_reason = migration.get("migration_reason", "unknown")
            
            if migration_reason == "server_failed":
                if migration.get("is_cold_migration", False):
                    original_reason = "server_failed_unpredicted"
                else:
                    original_reason = "low_reliability"
            elif migration_reason in ["low_reliability", "delay_violation", "predicted_failure"]:
                original_reason = migration_reason
            else:
                original_reason = migration_reason if migration_reason != "unknown" else "unclassified"
        
        # ─────────────────────────────────────────────────────────────
        # PROVISIONAMENTO (origin = None)
        # ─────────────────────────────────────────────────────────────
        if is_provisioning:
            if status == "waiting":
                return "provisioning_waiting_in_download_queue"
            
            elif status == "pulling_layers":
                return "provisioning_downloading_layers"
            
            else:
                print(f"[CLASSIFY_DOWNTIME] ⚠️ Provisionamento com status inesperado: '{status}' (Service {service.id})")
                return f"provisioning_{status}"
        
        # ─────────────────────────────────────────────────────────────
        # MIGRAÇÃO (origin != None)
        # ─────────────────────────────────────────────────────────────
        else:
            prefix = f"migration_{original_reason}"
            
            if status == "waiting":
                return f"{prefix}_waiting_in_download_queue"
            
            elif status == "pulling_layers":
                if is_live_migration_enabled:
                    origin_available = origin.available if origin else False
                    
                    if not origin_available:
                        return f"{prefix}_downloading_layers_cold"
                    else:
                        print(f"[CLASSIFY_DOWNTIME] ⚠️ Live Migration mas serviço indisponível durante download!")
                        print(f"                    Service {service.id}, Origin {origin.id} (available={origin.available})")
                        return f"{prefix}_downloading_layers_transition"
                else:
                    return f"{prefix}_downloading_layers_cold"
            
            elif status == "migrating_service_state":
                return f"{prefix}_cutover"
            
            else:
                print(f"[CLASSIFY_DOWNTIME] ⚠️ Migração com status inesperado: '{status}' (Service {service.id})")
                print(f"                    Original reason: {original_reason}, Origin: {origin.id if origin else 'None'}")
                
                if status == "finished":
                    return "service_startup_delay"
                elif status == "interrupted":
                    return "server_failure_orphaned"
                else:
                    return f"{prefix}_{status}"
    
    # ✅ CASO 4: Serviço indisponível (sem migração detectada explicitamente)
    if unavailability_reason == "service_not_available":
        if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
            last_migration = service._Service__migrations[-1]
            
            if last_migration.get("end") is None:
                print(f"[CLASSIFY_DOWNTIME] ⚠️ 'service_not_available' mas migração ativa! (Service {service.id})")
                print(f"                    Status: {last_migration.get('status')}, Origin: {last_migration.get('origin')}")
                
                return _classify_downtime_cause_v2(user, app, service, current_step, "migration_in_progress")
            
            if last_migration.get("status") == "interrupted":
                return "server_failure_orphaned"
            
            if last_migration.get("status") == "finished":
                return "service_startup_delay"
        
        return "provisioning_initial"
    
    # ✅ CASO NÃO PREVISTO: CAPTURAR DETALHES COMPLETOS
    print(f"[CLASSIFY_DOWNTIME] ⚠️⚠️⚠️ CASO NÃO CLASSIFICADO DETECTADO!")
    print(f"                    Razão: '{unavailability_reason}' (Service {service.id}, App {app.id})")
    print(f"                    User {user.id}, Step {current_step}")
    
    # ✅ CAPTURAR ESTADO COMPLETO DO SERVIÇO
    debug_info = {
        'step': current_step,
        'user_id': user.id,
        'app_id': app.id,
        'service_id': service.id,
        'unavailability_reason': unavailability_reason,
        'service_available': service._available,
        'server': service.server.id if service.server else None,
        'server_available': service.server.available if service.server else None,
        'has_migrations': hasattr(service, '_Service__migrations'),
        'migrations_count': len(service._Service__migrations) if hasattr(service, '_Service__migrations') else 0,
    }
    
    # ✅ DETALHES DA ÚLTIMA MIGRAÇÃO (se existir)
    if hasattr(service, '_Service__migrations') and len(service._Service__migrations) > 0:
        last_mig = service._Service__migrations[-1]
        debug_info['last_migration'] = {
            'status': last_mig.get('status'),
            'origin': last_mig.get('origin').id if last_mig.get('origin') else None,
            'target': last_mig.get('target').id if last_mig.get('target') else None,
            'start': last_mig.get('start'),
            'end': last_mig.get('end'),
            'migration_reason': last_mig.get('migration_reason'),
            'original_migration_reason': last_mig.get('original_migration_reason'),
        }
    
    print(f"                    Debug Info: {debug_info}")
    
    # ✅ Armazenar para análise posterior
    _unclassified_cases.append(debug_info)
    
    return "downtime_unclassified"

def print_unclassified_downtime_report():
    """
    Imprime relatório detalhado dos casos não classificados.
    Executar ao final da simulação para diagnóstico.
    """
    global _unclassified_cases
    
    if not _unclassified_cases:
        print("\n✅ Nenhum caso de downtime não classificado detectado!")
        return
    
    print(f"\n{'='*80}")
    print(f"RELATÓRIO DE CASOS NÃO CLASSIFICADOS ({len(_unclassified_cases)} casos)")
    print(f"{'='*80}\n")
    
    # ✅ Agrupar por 'unavailability_reason'
    by_reason = {}
    for case in _unclassified_cases:
        reason = case['unavailability_reason']
        if reason not in by_reason:
            by_reason[reason] = []
        by_reason[reason].append(case)
    
    for reason, cases in by_reason.items():
        print(f"\n📌 Razão: '{reason}' ({len(cases)} ocorrências)")
        print(f"   {'─'*70}")
        
        # Mostrar primeiros 3 casos
        for i, case in enumerate(cases[:3], 1):
            print(f"\n   Caso {i}:")
            print(f"     Step: {case['step']}")
            print(f"     Service: {case['service_id']} (User {case['user_id']}, App {case['app_id']})")
            print(f"     service._available: {case['service_available']}")
            print(f"     server: {case['server']} (available: {case['server_available']})")
            print(f"     Has migrations: {case['has_migrations']} (count: {case['migrations_count']})")
            
            if 'last_migration' in case:
                mig = case['last_migration']
                print(f"     Última migração:")
                print(f"       Status: {mig['status']}")
                print(f"       Origin: {mig['origin']} → Target: {mig['target']}")
                print(f"       Steps: {mig['start']} - {mig['end']}")
                print(f"       Reason: {mig['migration_reason']} (original: {mig['original_migration_reason']})")
        
        if len(cases) > 3:
            print(f"\n   ... e mais {len(cases) - 3} casos com mesma razão")
    
    print(f"\n{'='*80}\n")


# ============================================================================
# ✅ FUNÇÃO AUXILIAR: Validar Consistência de Rastreamento
# ============================================================================

def validate_tracking_consistency(current_step):
    """
    Valida consistência entre:
    - user.delays
    - service._available
    - server.available
    - Contadores de SLA violations
    - Contadores de downtime
    
    Executar periodicamente para detectar inconsistências.
    """
    if current_step % 100 != 0:
        return
    
    print(f"\n{'='*70}")
    print(f"[VALIDATION] === VALIDANDO CONSISTÊNCIA - STEP {current_step} ===")
    print(f"{'='*70}\n")
    
    inconsistencies = []
    
    for user in User.all():
        for app in user.applications:
            app_id = str(app.id)
            service = app.services[0]
            
            if not is_user_accessing_application(user, app, current_step):
                continue
            
            # ✅ Validação 1: delay = inf deve implicar serviço indisponível
            current_delay = user.delays.get(app_id, 0)
            is_available, _ = is_service_available_for_user(service, user, app, current_step)
            
            if current_delay == float('inf') and is_available:
                inconsistencies.append({
                    "type": "delay_availability_mismatch",
                    "user": user.id,
                    "app": app.id,
                    "service": service.id,
                    "detail": "delay=inf mas serviço marcado como disponível"
                })
            
            # ✅ Validação 2: serviço disponível deve ter delay finito
            if is_available and current_delay == float('inf'):
                inconsistencies.append({
                    "type": "availability_delay_mismatch",
                    "user": user.id,
                    "app": app.id,
                    "service": service.id,
                    "detail": "serviço disponível mas delay=inf"
                })
            
            # ✅ Validação 3: servidor indisponível deve resultar em delay=inf
            if service.server and not service.server.available and current_delay != float('inf'):
                inconsistencies.append({
                    "type": "server_unavailable_but_delay_finite",
                    "user": user.id,
                    "app": app.id,
                    "service": service.id,
                    "server": service.server.id,
                    "delay": current_delay
                })
    
    if inconsistencies:
        print(f"[VALIDATION] ⚠️ {len(inconsistencies)} INCONSISTÊNCIAS DETECTADAS:")
        for inc in inconsistencies[:10]:  # Mostrar primeiras 10
            print(f"  - {inc['type']}: User {inc['user']}, App {inc['app']}, Service {inc['service']}")
            print(f"    Detalhe: {inc.get('detail', 'N/A')}")
        
        if len(inconsistencies) > 10:
            print(f"  ... e mais {len(inconsistencies) - 10} inconsistências")
    else:
        print(f"[VALIDATION] ✅ Nenhuma inconsistência detectada")
    
    print(f"\n{'='*70}\n")
    
    return inconsistencies


def diagnose_downtime_sla_violations():
    """
    Diagnostica violações de SLA de downtime para detectar problemas.
    Executar ao final da simulação.
    """
    print(f"\n{'='*70}")
    print(f"DIAGNÓSTICO DE VIOLAÇÕES DE SLA DE DOWNTIME")
    print(f"{'='*70}\n")
    
    total_sessions = 0
    sessions_with_downtime = 0
    sessions_violating_sla = 0
    
    # ✅ DEBUG: Verificar se user_perceived_downtime_history está populado
    users_with_history = 0
    total_history_entries = 0
    
    for user in User.all():
        if hasattr(user, 'user_perceived_downtime_history') and user.user_perceived_downtime_history:
            users_with_history += 1
            for app_id, history in user.user_perceived_downtime_history.items():
                total_history_entries += len(history)
    
    print(f"[DIAGNOSE] Usuários com histórico: {users_with_history}/{len(User.all())}")
    print(f"[DIAGNOSE] Total de entradas de histórico: {total_history_entries}")
    
    if total_history_entries == 0:
        print(f"\n⚠️⚠️⚠️ PROBLEMA CRÍTICO: user_perceived_downtime_history está VAZIO!")
        print(f"   Isso impede o cálculo de violações de SLA de downtime por sessão.")
        print(f"   Verifique se update_user_perceived_downtime_for_current_step() está sendo chamado a cada step.\n")
        print(f"{'='*70}\n")
        return
    
    for user in User.all():
        for app in user.applications:
            app_id = str(app.id)
            
            # Obter metadados
            access_pattern = user.access_patterns[app_id]
            downtime_sla = user.maximum_downtime_allowed.get(app_id, float('inf'))
            
            # Verificar histórico de acessos
            if not access_pattern.history:
                continue
            
            # Analisar cada sessão
            for session in access_pattern.history:
                session_start = session.get('start')
                session_end = session.get('end')
                
                if session_start is None or session_end is None:
                    continue
                
                total_sessions += 1
                
                # Calcular downtime desta sessão
                session_downtime = 0
                
                if (hasattr(user, 'user_perceived_downtime_history') and 
                    app_id in user.user_perceived_downtime_history):
                    downtime_history = user.user_perceived_downtime_history[app_id]
                    
                    for step in range(session_start, session_end + 1):
                        step_index = step - 1
                        if step_index < len(downtime_history):
                            if downtime_history[step_index]:
                                session_downtime += 1
                
                if session_downtime > 0:
                    sessions_with_downtime += 1
                
                if session_downtime > downtime_sla:
                    sessions_violating_sla += 1
                    
                    # Log primeiras 10 violações
                    if sessions_violating_sla <= 10:
                        duration = session_end - session_start + 1
                        print(f"  Violação {sessions_violating_sla}:")
                        print(f"    User {user.id}, App {app.id}")
                        print(f"    Sessão: steps {session_start}-{session_end} (duração: {duration})")
                        print(f"    Downtime: {session_downtime} steps (SLA: {downtime_sla})")
    
    print(f"\n📊 RESUMO:")
    print(f"  Total de sessões: {total_sessions}")
    print(f"  Sessões com downtime: {sessions_with_downtime} ({sessions_with_downtime/total_sessions*100:.1f}% se total_sessions > 0 else 0)")
    print(f"  Sessões violando SLA: {sessions_violating_sla} ({sessions_violating_sla/total_sessions*100:.1f}% se total_sessions > 0 else 0)")
    
    if sessions_violating_sla == 0 and sessions_with_downtime > 0:
        print(f"\n⚠️ ALERTA: Há downtime mas NENHUMA violação de SLA!")
        print(f"   Possível causa: downtime_sla muito alto ou histórico incompleto")
    
    print(f"\n{'='*70}\n")