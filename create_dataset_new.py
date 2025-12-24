"""This script will be responsible for creating EdgeSimPy dataset files"""

# Importing EdgeSimPy components
from edge_sim_py import *

# Importing custom project components
from simulator.extensions.base_failure_model import BaseFailureGroupModel
from simulator.helper_functions import *

# Importing Python modules
from random import seed, sample, randint
import matplotlib.pyplot as plt
import networkx as nx
import json
import copy


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


def edge_server_to_dict(self) -> dict:
    """Method that overrides the way the object is formatted to JSON."

    Returns:
        dict: JSON-friendly representation of the object as a dictionary.
    """
    dictionary = {
        "attributes": {
            "id": self.id,
            "model_name": self.model_name,
            "cpu": self.cpu,
            "memory": self.memory,
            "disk": self.disk,
            "cpu_demand": self.cpu_demand,
            "memory_demand": self.memory_demand,
            "disk_demand": self.disk_demand,
            "coordinates": self.coordinates,
            "max_concurrent_layer_downloads": self.max_concurrent_layer_downloads,
            "active": self.active,
            "power_model_parameters": self.power_model_parameters,
            "time_to_boot": self.time_to_boot,
            "status": self.status,
            "available": self.available,
        },
        "relationships": {
            "failure_model": {"class": type(self.failure_model).__name__, "id": self.failure_model.id} if self.failure_model else None,
            "power_model": self.power_model.__name__ if self.power_model else None,
            "base_station": {"class": type(self.base_station).__name__, "id": self.base_station.id} if self.base_station else None,
            "network_switch": {"class": type(self.network_switch).__name__, "id": self.network_switch.id} if self.network_switch else None,
            "services": [{"class": type(service).__name__, "id": service.id} for service in self.services],
            "container_layers": [{"class": type(layer).__name__, "id": layer.id} for layer in self.container_layers],
            "container_images": [{"class": type(image).__name__, "id": image.id} for image in self.container_images],
            "container_registries": [{"class": type(reg).__name__, "id": reg.id} for reg in self.container_registries],
        },
    }
    return dictionary


def user_to_dict(self) -> dict:
    access_patterns = {}
    for app_id, access_pattern in self.access_patterns.items():
        access_patterns[app_id] = {"class": access_pattern.__class__.__name__, "id": access_pattern.id}

    dictionary = {
        "attributes": {
            "id": self.id,
            "coordinates": self.coordinates,
            "coordinates_trace": self.coordinates_trace,
            "delays": copy.deepcopy(self.delays),
            "delay_slas": copy.deepcopy(self.delay_slas),
            "maximum_downtime_allowed": copy.deepcopy(self.maximum_downtime_allowed),
            "communication_paths": copy.deepcopy(self.communication_paths),
            "making_requests": copy.deepcopy(self.making_requests),
            "mobility_model_parameters": copy.deepcopy(self.mobility_model_parameters) if self.mobility_model_parameters else {},
        },
        "relationships": {
            "access_patterns": access_patterns,
            "mobility_model": self.mobility_model.__name__,
            "applications": [{"class": type(app).__name__, "id": app.id} for app in self.applications],
            "base_station": {"class": type(self.base_station).__name__, "id": self.base_station.id},
        },
    }
    return dictionary


# Defining a seed value to enable reproducibility
seed(0)

# Creating list of map coordinates
map_coordinates = hexagonal_grid(x_size=25, y_size=25)

# Creating base stations for providing wireless connectivity to users and network switches for wired connectivity
for coordinates_id, coordinates in enumerate(map_coordinates):
    # Creating a base station object
    base_station = BaseStation()
    base_station.wireless_delay = 0
    base_station.coordinates = coordinates

    # Creating a network switch object using the "sample_switch()" generator, which embeds built-in power consumption specs
    network_switch = sample_switch()
    base_station._connect_to_network_switch(network_switch=network_switch)
    base_station.has_registry = False  # This attribute will be properly defined later
# Creating a partially-connected mesh network topology
partially_connected_hexagonal_mesh(
    network_nodes=NetworkSwitch.all(),
    link_specifications=[
        {
            "number_of_objects": 1776,
            "delay": 3,
            "bandwidth": 100,
            "transmission_delay": 0.06,  # Value in seconds
        },
    ],
)

SERVERS_PER_SPEC = 10
edge_server_specifications = [
    {
        "number_of_objects": SERVERS_PER_SPEC,
        "model_name": "PowerEdge R620",
        "cpu": 16,
        "memory": 24,
        "disk": 131072,  # 128 GB
        "static_power_percentage": 54.1 / 243,
        "max_power_consumption": 243,
        # Failure-related parameters:
        "time_to_boot": 10,
        "initial_failure_time_step": randint(1, 20),
        "number_of_failures": {"lower_bound": 1, "upper_bound": 5},
        "failure_duration": {"lower_bound": 50, "upper_bound": 100},
        "interval_between_failures": {"lower_bound": 10, "upper_bound": 30},
        "interval_between_sets": {"lower_bound": 10, "upper_bound": 30},
    },
    {
        "number_of_objects": SERVERS_PER_SPEC,
        "model_name": "SGI",
        "cpu": 32,
        "memory": 32,
        "disk": 131072,  # 128 GB
        "static_power_percentage": 265 / 1387,
        "max_power_consumption": 1387,
        # Failure-related parameters:
        "time_to_boot": 10,
        "initial_failure_time_step": randint(1, 30),
        "number_of_failures": {"lower_bound": 2, "upper_bound": 4},
        "failure_duration": {"lower_bound": 10, "upper_bound": 50},
        "interval_between_failures": {"lower_bound": 100, "upper_bound": 200},
        "interval_between_sets": {"lower_bound": 100, "upper_bound": 200},
    },
    {
        "number_of_objects": SERVERS_PER_SPEC,
        "model_name": "Proliant",
        "cpu": 36,
        "memory": 64,
        "disk": 131072,  # 128 GB
        "static_power_percentage": 45 / 276,
        "max_power_consumption": 276,
        # Failure-related parameters:
        "time_to_boot": 5,
        "initial_failure_time_step": randint(1, 100),
        "number_of_failures": {"lower_bound": 1, "upper_bound": 2},
        "failure_duration": {"lower_bound": 10, "upper_bound": 20},
        "interval_between_failures": {"lower_bound": 150, "upper_bound": 250},
        "interval_between_sets": {"lower_bound": 150, "upper_bound": 250},
    },
    {
        "number_of_objects": 1,
        "model_name": "Jetson TX2",
        "cpu": 6,
        "memory": 8,
        "disk": 131072,  # 128 GB
        "static_power_percentage": 7.5 / 15,
        "max_power_consumption": 15,
        # Failure-related parameters:
        "time_to_boot": 1,
        "initial_failure_time_step": float("inf"),  # This server will never fail
        "number_of_failures": {"lower_bound": 0, "upper_bound": 0},
        "failure_duration": {"lower_bound": 0, "upper_bound": 0},
        "interval_between_failures": {"lower_bound": 0, "upper_bound": 0},
        "interval_between_sets": float("inf"),  # This server will never fail
    },
]

# Creating edge servers
for spec in edge_server_specifications:
    for _ in range(spec["number_of_objects"]):
        # Creating an edge server
        server = EdgeServer()
        server.model_name = spec["model_name"]

        # Computational capacity (CPU in number of cores, RAM in gigabytes, and disk in megabytes)
        server.cpu = spec["cpu"]
        server.memory = spec["memory"]
        server.disk = spec["disk"]

        # Power-related attributes
        server.power_model = LinearServerPowerModel
        server.power_model_parameters = {
            "static_power_percentage": spec["static_power_percentage"],
            "max_power_consumption": spec["max_power_consumption"],
        }

        # Connecting the edge server to a random base station that has no edge server connected to it yet
        base_station = sample([base_station for base_station in BaseStation.all() if len(base_station.edge_servers) == 0], 1)[0]
        base_station._connect_to_edge_server(edge_server=server)
        if server.model_name == "Jetson TX2":
            server.base_station.has_registry = True  # The Jetson TX2 server will host a container registry
        else:
            server.base_station.has_registry = False

        # Failure-related attributes
        server.time_to_boot = spec["time_to_boot"]
        server.status = "available"
        server.available = True

        # Defining the failure trace
        initial_failure_time_step = spec["initial_failure_time_step"]
        if server.model_name != "Jetson TX2":
            initial_failure_time_step = -2550
        
        print(f"[LOG] Creating failure model for {server.model_name} with initial_failure_time_step: {initial_failure_time_step}")
        
        BaseFailureGroupModel(
            device=server,
            initial_failure_time_step=initial_failure_time_step,
            failure_characteristics={
                "number_of_failures": spec["number_of_failures"],
                "failure_duration": spec["failure_duration"],
                "interval_between_failures": spec["interval_between_failures"],
                "interval_between_sets": spec["interval_between_sets"],
            },
            number_of_failure_groups_to_create=50 if server.model_name != "Jetson TX2" else 0,  # The Jetson TX2 server will never fail
        )
        # Creating the failure history (only for failures that started before the simulation began - "becomes_available_at" < 0)
        # and defining status and availability according to failure history.
        should_halt_failure_loops = False
        server.failure_model.failure_history = []
        for failure_group in server.failure_model.failure_trace:
            if should_halt_failure_loops:
                break
            for failure in failure_group:
                if failure["becomes_available_at"] < 0:
                    server.failure_model.failure_history.append(failure)
                else:
                    if failure["starts_booting_at"] <= 0 and failure["finishes_booting_at"] > 0:
                        server.status = "booting"
                        server.available = False
                    elif failure["failure_starts_at"] <= 0:
                        server.status = "failing"
                        server.available = False
                    # print("\n")
                    # print(server)
                    # print(server.status)
                    # print(server.available)
                    
                    # print(failure)
                    # print("\n")
                    should_halt_failure_loops = True
                    break


#display_topology(topology=Topology.first())
for base_station in BaseStation.all():
    print(f"[LOG] {base_station} - Has registry? {base_station.has_registry} - Edge servers: {base_station.edge_servers}")

# Reading specifications for container images and container registries
with open("container_images.json", "r", encoding="UTF-8") as read_file:
    container_image_specifications = json.load(read_file)

# Manually including a "registry" image specification that is used by container registries within the infrastructure
container_registry_image = {
    "name": "registry",
    "digest": "sha256:0f7e78",
    "layers": [
        {
            "digest": "sha256:31e352",
            "size": round(3.2404699325561523, 2),
        },
        {
            "digest": "sha256:3c98a1",
            "size": round(5.634401321411133, 2),
        },
    ],
}
container_image_specifications.append(container_registry_image)

# Defining service image specifications
service_image_specifications = [
    ###########################
    #### Operating Systems ####
    ###########################
    {"state": 0, "image_name": "debian"},
    {"state": 0, "image_name": "centos"},
    {"state": 0, "image_name": "ubuntu"},
    {"state": 0, "image_name": "fedora"},
    ###########################
    #### Language Runtimes ####
    ###########################
    {"state": 0, "image_name": "erlang"},
    {"state": 0, "image_name": "perl"},
    {"state": 0, "image_name": "python"},
    {"state": 0, "image_name": "elixir"},
    ##############################
    #### Generic Applications ####
    ##############################
    {"state": 0, "image_name": "flink"},  # Streaming
    {"state": 0, "image_name": "couchbase"},  # Database noSQL
]

# Adding a "latest" tag to all container images
condensed_images_metadata = []
for container_image in container_image_specifications:
    container_image["tag"] = "latest"
    condensed_images_metadata.append(
        {
            "name": container_image["name"],
            "tag": container_image["tag"],
            "layers": container_image["layers"],
        }
    )

container_registry_specifications = [
    {
        "number_of_objects": 1,
        "images": condensed_images_metadata,
        "cpu_demand": 6,
        "memory_demand": 8,
    },
]

# Parsing the specifications for container images and container registries
registries = create_container_registries(
    container_registry_specifications=container_registry_specifications,
    container_image_specifications=container_image_specifications,
)

# Creating container registries and accommodating them within the infrastructure
for index, registry_spec in enumerate(container_registry_specifications):
    # Creating an edge server to host the registry
    registry_base_station = [bs for bs in BaseStation.all() if bs.has_registry][0]
    registry_host = registry_base_station.edge_servers[0]
    registry_base_station._connect_to_edge_server(edge_server=registry_host)

    # Updating the registry CPU and RAM demand to fill its host
    registries[index]["cpu_demand"] = registry_spec["cpu_demand"]
    registries[index]["memory_demand"] = registry_spec["memory_demand"]

    # Creating the registry object
    provision_container_registry(container_registry_specification=registries[index], server=registry_host)
    
    # Coletar TODAS as imagens template disponíveis
    all_template_images = [img for img in ContainerImage.all()]
    
    # Mostrar as imagens
    for img in all_template_images:
        print(f"  - {img.name}:{img.tag} (digest: {img.digest[:12]}..., {len(img.layers_digests)} camadas)")
    
    # Coletar TODAS as camadas únicas de todas as imagens
    all_unique_layers = {}
    
    for template_image in all_template_images:
        for layer_digest in template_image.layers_digests:
            if layer_digest not in all_unique_layers:
                # Buscar a camada template original
                template_layer = ContainerLayer.find_by(attribute_name="digest", attribute_value=layer_digest)
                if template_layer:
                    all_unique_layers[layer_digest] = template_layer
    
    layers_added = 0
    layers_skipped = 0
    total_size_added = 0
    
    for layer_digest, template_layer in all_unique_layers.items():
        # Verificar se camada já existe no servidor
        layer_exists = any(
            l.digest == layer_digest 
            for l in registry_host.container_layers
        )
        
        if not layer_exists:
            # Criar nova instância da camada no servidor do Registry
            registry_layer = ContainerLayer(
                digest=template_layer.digest,
                size=template_layer.size,
                instruction=template_layer.instruction,
            )
            
            if hasattr(registry_host, 'model') and registry_host.model:
                registry_host.model.initialize_agent(agent=registry_layer)
            
            # Marcar a camada como pertencente ao servidor
            registry_layer.server = registry_host
            
            # Adicionar ao servidor do Registry
            registry_host.container_layers.append(registry_layer)
            
            # Reservar espaço em disco
            registry_host.disk_demand += registry_layer.size
            
            layers_added += 1
            total_size_added += registry_layer.size
            
            # Log detalhado apenas para as primeiras 5 camadas
            if layers_added <= 5:
                print(f"  [{layers_added:3d}] ✓ {layer_digest[:12]}... ({registry_layer.size:6.2f} MB) - {registry_layer.instruction}")
        else:
            layers_skipped += 1
            if layers_skipped <= 3:
                print(f"        - {layer_digest[:12]}... (já existe)")
    
    # Mostrar resumo
    if layers_added > 5:
        print(f"  ... ({layers_added - 5} camadas adicionais)")
    
    print(f"\n[REGISTRY_SETUP] {'='*80}")
    print(f"[REGISTRY_SETUP] RESUMO DA POPULAÇÃO:")
    print(f"  ✓ Camadas ADICIONADAS: {layers_added}")
    print(f"  - Camadas JÁ EXISTENTES: {layers_skipped}")
    print(f"  = TOTAL no servidor: {len(registry_host.container_layers)}")
    print(f"  📦 Tamanho adicionado: {total_size_added:.2f} MB")
    print(f"  💾 Disk demand: {registry_host.disk_demand:.2f} MB / {registry_host.disk} MB ({(registry_host.disk_demand/registry_host.disk)*100:.1f}%)")
    print(f"{'='*80}")
    
    # ✅ VALIDAÇÃO: Verificar se todas as imagens têm suas camadas
    print(f"\n[REGISTRY_VALIDATION] Validando integridade das imagens...")
    
    all_valid = True
    for img in registry_host.container_images:
        missing_layers = []
        for layer_digest in img.layers_digests:
            if not any(l.digest == layer_digest for l in registry_host.container_layers):
                missing_layers.append(layer_digest[:12])
        
        if missing_layers:
            print(f"  ⚠️ {img.name}:{img.tag} - FALTAM {len(missing_layers)} camadas: {missing_layers}")
            all_valid = False
        else:
            print(f"  ✓ {img.name}:{img.tag} - COMPLETA ({len(img.layers_digests)} camadas)")
    
    if all_valid:
        print(f"\n[REGISTRY_VALIDATION] ✅ TODAS AS IMAGENS ESTÃO COMPLETAS!")
    else:
        print(f"\n[REGISTRY_VALIDATION] ⚠️ ALGUMAS IMAGENS ESTÃO INCOMPLETAS!")
    
    print(f"{'='*80}\n")

# 3GPP. “5G; Service requirements for the 5G system (3GPP TS 22.261 version 16.16.0 Release 16)”,
# Technical specification (ts), 3rd Generation Partnership Project (3GPP), 2022, 72p.
# https://www.etsi.org/deliver/etsi_ts/122200_122299/122261/16.16.00_60/ts_122261v161600p.pdf
delay_slas = [
    20,  # Remote drone operation (page 52)
    30,  # Remote surgery (page 52)
]
maximum_downtime_allowed_specifications = [
    100,
    200,
]

SERVICES_PER_SPEC = 6

# We are considering monolith applications, so the cardinality of users, applications, and services is the same.
TOTAL_USERS_APPS_SERVICES = len(service_image_specifications) * SERVICES_PER_SPEC

access_pattern_specifications = [
    {
        "class": CircularDurationAndIntervalAccessPattern,
        "duration_values": [10, 20],  # How long the user will access the application at each call (Short-lived applications)
        "interval_values": [120, 120],  # Interval (in time steps) between the user accesses
    },
    {
        "class": CircularDurationAndIntervalAccessPattern,
        "duration_values": [60, 100],  # How long the user will access the application at each call (Long-lived applications)
        "interval_values": [40, 40],  # Interval (in time steps) between the user accesses
    },
]
service_demands = [
    {"cpu_demand": 1, "memory_demand": 1},
    {"cpu_demand": 2, "memory_demand": 2},
    {"cpu_demand": 4, "memory_demand": 4},
    {"cpu_demand": 8, "memory_demand": 8},
]

service_image_specification_values = uniform(n_items=TOTAL_USERS_APPS_SERVICES, valid_values=service_image_specifications)
access_pattern_specification_values = uniform(n_items=TOTAL_USERS_APPS_SERVICES, valid_values=access_pattern_specifications)


# Creating service and user objects
for instance_index, service_spec in enumerate(service_image_specification_values):
    # Creating the application object
    app = Application()

    # Creating the user that access the application
    user = User()

    user.communication_paths[str(app.id)] = []
    user.delays[str(app.id)] = None

    # Creating the "maximum_downtime_allowed" property
    user.maximum_downtime_allowed = {}

    # Defining user's coordinates and connecting him to a base station
    user.mobility_model = pathway
    random_base_station = sample(BaseStation.all(), 1)[0]
    user._set_initial_position(coordinates=random_base_station.coordinates, number_of_replicates=2)

    # Defining the user's access pattern
    user_access_pattern = access_pattern_specification_values[instance_index]
    start = randint(2, 30)  # Randomizing the time step when the user will start accessing the application
    user_access_pattern["class"](
        user=user,
        app=app,
        start=start,
        duration_values=user_access_pattern["duration_values"],
        interval_values=user_access_pattern["interval_values"],
    )
    # Defining the relationship attributes between the user and the application
    user.applications.append(app)
    app.users.append(user)

    # Gathering information on the service image based on the specified 'name' parameter
    service_image = next((img for img in ContainerImage.all() if img.name == service_spec["image_name"]), None)

    # Creating the service object
    service = Service(
        image_digest=service_image.digest,
        cpu_demand=0,  # This attribute will be properly defined later
        memory_demand=0,  # This attribute will be properly defined later
        state=service_spec["state"],
    )

    # Connecting the application to its new service
    app.connect_to_service(service)

# Defining application delay SLAs and maximum downtime allowed values
applications_sorted_randomly = sample(Application.all(), Application.count())
delay_sla_values = uniform(n_items=Application.count(), valid_values=delay_slas)
maximum_downtime_allowed_values = uniform(n_items=Application.count(), valid_values=maximum_downtime_allowed_specifications)

for index, application in enumerate(applications_sorted_randomly):
    application.users[0].delay_slas[str(application.id)] = delay_sla_values[index]
    application.users[0].maximum_downtime_allowed[str(application.id)] = maximum_downtime_allowed_values[index]

# Defining service demands
services_sorted_randomly = sample(Service.all(), Service.count())
service_demand_values = uniform(n_items=Service.count(), valid_values=service_demands)
for index, service in enumerate(services_sorted_randomly):
    service.cpu_demand = service_demand_values[index]["cpu_demand"]
    service.memory_demand = service_demand_values[index]["memory_demand"]
    service._available = True
    service.being_provisioned = False

# Armazenando todas as imagens templates disponíveis no Registry
    
# Coletar TODAS as imagens disponíveis (templates)
all_template_images = [img for img in ContainerImage.all()]

# Para cada imagem template, criar uma instância no Registry
for template_image in all_template_images:
    # Verificar se imagem já existe no Registry
    image_exists = any(
        img.digest == template_image.digest 
        for img in registry_host.container_images
    )
    
    if not image_exists:
        # Criar nova instância da imagem no Registry
        registry_image = ContainerImage()
        registry_image.name = template_image.name
        registry_image.digest = template_image.digest
        registry_image.tag = template_image.tag
        registry_image.architecture = template_image.architecture
        registry_image.layers_digests = copy.deepcopy(template_image.layers_digests)
        registry_image.server = registry_host
        
        # Adicionar ao Registry
        registry_host.container_images.append(registry_image)

# Defining the initial service placement
randomized_closest_fit()

# Updating service availability based on server status
for service in Service.all():
    service._available = service.server.available if service.server else False

# Calculating user communication paths and application delays
for user in User.all():
    for application in user.applications:
        user.set_communication_path(app=application)


###############################################
#### WRAPPING UP AND EXPORTING THE DATASET ####
###############################################
# Displaying the scenario's base information
show_scenario_overview()

# Instructing EdgeSimPy to serialize objects with the new attributes
EdgeServer._to_dict = edge_server_to_dict
User._to_dict = user_to_dict

# Exporting scenario
ComponentManager.export_scenario(save_to_file=True, file_name="dataset_extended")

# Exporting the topology representation to an image file
#display_topology(topology=Topology.first())
