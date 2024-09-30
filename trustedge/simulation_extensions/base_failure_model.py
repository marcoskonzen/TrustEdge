# Importing Python modules
from random import randint
from json import dumps
from edge_sim_py.components.edge_server import EdgeServer


class BaseFailureGroupModel:
    def __init__(self, device: object = None, initial_failure_time_step: int = 1, failure_characteristics: dict = {}):
        # Device to whom the failure group pattern is attached to
        self.device = device
        if device is not None:
            self.device.failure_model = self

        # List of historical failure occurrences and the planned failures
        self.failure_history = []  # The failure history attribute comprises only failures that already occurred
        self.failure_trace = []  # The failure trace attribute comprises both failures that occurred and are planned to occur

        # Failure characteristics
        self.failure_characteristics = failure_characteristics

        # Creating the first failure based on the passed failure characteristics
        self.generate_failure_set(next_failure_time_step=initial_failure_time_step)

    def generate_failure_set(self, next_failure_time_step: int):
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
                if failure_group[-1]["failure_ends_at"] == float("inf") or self.failure_characteristics["interval_between_failures"] == float("inf"):
                    break

                # The subsequent failure starts at a predefined interval after the previous failure
                interval_from_last_failure = randint(
                    a=self.failure_characteristics["interval_between_failures"]["lower_bound"],
                    b=self.failure_characteristics["interval_between_failures"]["upper_bound"],
                )
                failure["failure_starts_at"] = failure_group[-1]["failure_ends_at"] + interval_from_last_failure + 1

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


def main():
    # Creating a sample edge server for testing purposes
    sample_edge_server = EdgeServer()
    sample_edge_server.time_to_boot = 2

    # Create an instance of the BaseFailureGroupModel class
    failure_group_model = BaseFailureGroupModel(
        device=sample_edge_server,
        initial_failure_time_step=1,
        failure_characteristics={
            "number_of_failures": {"lower_bound": 3, "upper_bound": 3},
            "failure_duration": {"lower_bound": 5, "upper_bound": 5},
            "interval_between_failures": {"lower_bound": 4, "upper_bound": 4},
            "interval_between_sets": {"lower_bound": 8, "upper_bound": 8},
        },
    )

    failure_group_model.generate_failure_set(next_failure_time_step=failure_group_model.failure_characteristics["interval_between_sets"])

    print(dumps(failure_group_model.failure_trace, indent=4))


if __name__ == "__main__":
    main()
