# EdgeSimPy components
from edge_sim_py.component_manager import ComponentManager

# Importing Python modules
from random import randint
from copy import deepcopy
from json import dumps


class BaseFailureGroupModel(ComponentManager):

    # Class attributes that allow this class to use helper methods from the ComponentManager
    _instances = []
    _object_count = 0

    def __init__(
        self,
        device: object = None,
        initial_failure_time_step: int = 1,
        failure_characteristics: dict = {},
        number_of_failure_groups_to_create: int = 1,
    ):
        # Adding the new object to the list of instances of its class
        self.__class__._instances.append(self)

        # Object's class instance ID
        self.__class__._object_count += 1
        self.id = self.__class__._object_count

        # Device to whom the failure group pattern is attached to
        self.device = device
        if device is not None:
            self.device.failure_model = self

        # List of historical failure occurrences and the planned failures
        self.failure_history = []  # The failure history attribute comprises only failures that already occurred
        self.failure_trace = []  # The failure trace attribute comprises both failures that occurred and are planned to occur

        # Failure characteristics
        self.initial_failure_time_step = initial_failure_time_step
        self.failure_characteristics = failure_characteristics

        # Creating the first failure based on the passed failure characteristics
        if failure_characteristics != {}:
            for count in range(number_of_failure_groups_to_create):
                interval_between_sets = randint(
                    a=self.failure_characteristics["interval_between_sets"]["lower_bound"],
                    b=self.failure_characteristics["interval_between_sets"]["upper_bound"],
                )

                if count == 0:
                    next_failure_time_step = initial_failure_time_step
                else:
                    if len(self.failure_trace) == 0:
                        next_failure_time_step = interval_between_sets
                    else:
                        next_failure_time_step = self.failure_trace[-1][-1]["becomes_available_at"] + interval_between_sets

                self.generate_failure_set(next_failure_time_step=next_failure_time_step)

    def _to_dict(self) -> dict:
        """Method that overrides the way the object is formatted to JSON."

        Returns:
            dict: JSON-friendly representation of the object as a dictionary.
        """
        dictionary = {
            "attributes": {
                "id": self.id,
                "initial_failure_time_step": self.initial_failure_time_step,
                "failure_history": self.failure_history,
                "failure_trace": self.failure_trace,
                "failure_characteristics": deepcopy(self.failure_characteristics),
            },
            "relationships": {
                "device": {"class": type(self.device).__name__, "id": self.device.id} if self.device else None,
            },
        }
        return dictionary

    def collect(self) -> dict:
        """Method that collects a set of metrics for the object.

        Returns:
            metrics (dict): Object metrics.
        """
        return {}

    def step(self):
        """Method that executes the events involving the object at each time step."""
        ...

    def generate_failure_set(self, next_failure_time_step: int):
        if next_failure_time_step != float("inf"):
            interval_between_sets_is_infinity = self.failure_characteristics["interval_between_sets"] == float("inf")
            last_failure_lasts_forever = len(self.failure_trace) > 0 and self.failure_trace[-1][-1]["failure_duration"] == float("inf")

            if len(self.failure_trace) > 0 and (interval_between_sets_is_infinity or last_failure_lasts_forever):
                return

            # Defining the number of failures that will compose the failure group
            number_of_failures_within_set = randint(
                a=self.failure_characteristics["number_of_failures"]["lower_bound"],
                b=self.failure_characteristics["number_of_failures"]["upper_bound"],
            )

            # Creating the failure group
            failure_group = []

            # Creating failures that will compose the failure group
            for failure_count in range(number_of_failures_within_set):
                # Accommodating the failure metadata within an independent dictionary
                failure = {}

                if failure_count == 0:
                    # The first failure starts at the initial failure time step
                    failure["failure_starts_at"] = next_failure_time_step
                else:
                    if failure_group[-1]["becomes_available_at"] == float("inf") or self.failure_characteristics["interval_between_failures"] == float("inf"):
                        break

                    # The subsequent failure starts at a predefined interval after the previous failure
                    interval_from_last_failure = randint(
                        a=self.failure_characteristics["interval_between_failures"]["lower_bound"],
                        b=self.failure_characteristics["interval_between_failures"]["upper_bound"],
                    )
                    failure["failure_starts_at"] = failure_group[-1]["becomes_available_at"] + interval_from_last_failure + 1

                if self.device.model is not None:
                    # Enforcing the failure start time step to be greater than the current time step to
                    # avoid issues considering the failure history prior the simulation beginning
                    if failure["failure_starts_at"] < self.device.model.schedule.steps + 1:
                        failure["failure_starts_at"] = self.device.model.schedule.steps + 2

                # Defining the duration and the end time step of the failure
                if self.failure_characteristics["failure_duration"] == float("inf"):
                    failure["failure_duration"] = float("inf")
                    failure["failure_ends_at"] = float("inf")
                else:
                    failure["failure_duration"] = randint(
                        a=self.failure_characteristics["failure_duration"]["lower_bound"],
                        b=self.failure_characteristics["failure_duration"]["upper_bound"],
                    )
                    failure["failure_ends_at"] = failure["failure_starts_at"] + failure["failure_duration"] - 1
                    failure["starts_booting_at"] = failure["failure_ends_at"] + 1
                    failure["finishes_booting_at"] = failure["starts_booting_at"] + self.device.time_to_boot - 1
                    failure["becomes_available_at"] = failure["finishes_booting_at"] + 1

                # Storing the failure metadata within the failure group list
                failure_group.append(failure)

            # Adding the created failure group to the failure history list
            self.failure_trace.append(failure_group)
