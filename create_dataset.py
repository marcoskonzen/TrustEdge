"""This script will be responsible for creating EdgeSimPy dataset files"""

# Importing EdgeSimPy components
from edge_sim_py import *

# Importing custom project components
from simulator.extensions.base_failure_model import BaseFailureGroupModel

# Importing Python libraries
from random import seed, sample
import matplotlib.pyplot as plt
import networkx as nx


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


###############################################
#### WRAPPING UP AND EXPORTING THE DATASET ####
###############################################

# Instructing EdgeSimPy to serialize EdgeServer objects with the new attributes
EdgeServer._to_dict = edge_server_to_dict

# Exporting scenario
ComponentManager.export_scenario(save_to_file=True, file_name="dataset1")

# Exporting the topology representation to an image file
display_topology(topology=Topology.first())
