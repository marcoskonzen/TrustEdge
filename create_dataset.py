"""This script will be responsible for creating EdgeSimPy dataset files"""

# Importing EdgeSimPy components
from edge_sim_py import *

# Importing custom project components
from simulator.extensions.base_failure_model import BaseFailureGroupModel
from simulator.helper_functions import *

# Importing Python libraries
from random import seed, sample
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
            "available": self.available,
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
map_coordinates = hexagonal_grid(x_size=4, y_size=4)

# Creating base stations for providing wireless connectivity to users and network switches for wired connectivity
for coordinates_id, coordinates in enumerate(map_coordinates):
    # Creating a base station object
    base_station = BaseStation()
    base_station.wireless_delay = 0
    base_station.coordinates = coordinates

    # Creating a network switch object using the "sample_switch()" generator, which embeds built-in power consumption specs
    network_switch = sample_switch()
    base_station._connect_to_network_switch(network_switch=network_switch)

# Creating a partially-connected mesh network topology
partially_connected_hexagonal_mesh(
    network_nodes=NetworkSwitch.all(),
    link_specifications=[
        {
            "number_of_objects": 33,
            "delay": 3,
            "bandwidth": 12.5,
            "transmission_delay": 0.06,  # Value in seconds
        },
    ],
)

SERVERS_PER_SPEC = 8
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
        "time_to_boot": 3,
        "initial_failure_time_step": 1,
        "number_of_failures": {"lower_bound": 3, "upper_bound": 3},
        "failure_duration": {"lower_bound": 5, "upper_bound": 5},
        "interval_between_failures": {"lower_bound": 4, "upper_bound": 4},
        "interval_between_sets": {"lower_bound": 8, "upper_bound": 8},
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
        "time_to_boot": 3,
        "initial_failure_time_step": 1,
        "number_of_failures": {"lower_bound": 3, "upper_bound": 3},
        "failure_duration": {"lower_bound": 5, "upper_bound": 5},
        "interval_between_failures": {"lower_bound": 4, "upper_bound": 4},
        "interval_between_sets": {"lower_bound": 8, "upper_bound": 8},
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

        # Failure-related attributes
        server.time_to_boot = spec["time_to_boot"]
        if spec["initial_failure_time_step"] > 1:
            server.status = "available"
        else:
            server.status = "failing"

        BaseFailureGroupModel(
            device=server,
            initial_failure_time_step=spec["initial_failure_time_step"],
            failure_characteristics={
                "number_of_failures": spec["number_of_failures"],
                "failure_duration": spec["failure_duration"],
                "interval_between_failures": spec["interval_between_failures"],
                "interval_between_sets": spec["interval_between_sets"],
            },
        )
        print(f"{server}. Failure Model: {server.failure_model}")

display_topology(topology=Topology.first())


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
            "size": 3.2404699325561523,
        },
        {
            "digest": "sha256:3c98a1",
            "size": 5.634401321411133,
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
        "base_station_id": 1,
        "images": condensed_images_metadata,
        "cpu_demand": 8,
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
    registry_base_station = BaseStation.find_by_id(registry_spec["base_station_id"])
    registry_host = registry_base_station.edge_servers[0]
    registry_base_station._connect_to_edge_server(edge_server=registry_host)

    # Updating the registry CPU and RAM demand to fill its host
    registries[index]["cpu_demand"] = registry_spec["cpu_demand"]
    registries[index]["memory_demand"] = registry_spec["memory_demand"]

    # Creating the registry object
    provision_container_registry(container_registry_specification=registries[index], server=registry_host)

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
        "class": RandomDurationAndIntervalAccessPattern,
        "duration_values": [15, 15],  # How long the user will access the application at each call (Short-lived applications)
        "interval_values": [60, 60],  # Interval (in time steps) between the user accesses
    },
    {
        "class": RandomDurationAndIntervalAccessPattern,
        "duration_values": [60, 60],  # How long the user will access the application at each call (Long-lived applications)
        "interval_values": [60, 60],  # Interval (in time steps) between the user accesses
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
    user_access_pattern["class"](
        user=user,
        app=app,
        start=1,
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

# Defining the initial service placement
randomized_closest_fit()

# Calculating user communication paths and application delays
for user in User.all():
    for application in user.applications:
        user.set_communication_path(app=application)


###############################################
#### WRAPPING UP AND EXPORTING THE DATASET ####
###############################################

# Instructing EdgeSimPy to serialize objects with the new attributes
EdgeServer._to_dict = edge_server_to_dict
User._to_dict = user_to_dict

# Exporting scenario
ComponentManager.export_scenario(save_to_file=True, file_name="dataset1")

# Exporting the topology representation to an image file
display_topology(topology=Topology.first())
