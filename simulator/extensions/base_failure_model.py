# EdgeSimPy components
from edge_sim_py.component_manager import ComponentManager

# Importing Python modules
from random import randint
from copy import deepcopy
from json import dumps
import numpy as np
from scipy import stats


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
                interval_between_sets = self._sample_interval_between_sets()

                if count == 0:
                    next_failure_time_step = initial_failure_time_step
                else:
                    if len(self.failure_trace) == 0:
                        next_failure_time_step = interval_between_sets
                    else:
                        next_failure_time_step = self.failure_trace[-1][-1]["becomes_available_at"] + interval_between_sets

                self.generate_failure_set(next_failure_time_step=next_failure_time_step)

    def _sample_interval_between_sets(self) -> int:
        """Amostra o intervalo entre grupos de falhas (uniforme)."""
        chars = self.failure_characteristics.get("interval_between_sets", {})
        if isinstance(chars, dict):
            return randint(
                a=chars.get("lower_bound", 10),
                b=chars.get("upper_bound", 100),
            )
        return chars if chars != float("inf") else float("inf")

    def _sample_interval_between_failures(self) -> int:
        """Amostra o intervalo entre falhas dentro de um grupo (uniforme)."""
        chars = self.failure_characteristics.get("interval_between_failures", {})
        if isinstance(chars, dict):
            return randint(
                a=chars.get("lower_bound", 10),
                b=chars.get("upper_bound", 50),
            )
        return chars if chars != float("inf") else float("inf")

    def _sample_failure_duration(self) -> int:
        """Amostra a duração de uma falha (uniforme)."""
        chars = self.failure_characteristics.get("failure_duration", {})
        if isinstance(chars, dict):
            return randint(
                a=chars.get("lower_bound", 10),
                b=chars.get("upper_bound", 100),
            )
        return chars if chars != float("inf") else float("inf")

    def _sample_number_of_failures(self) -> int:
        """Amostra o número de falhas em um grupo (uniforme)."""
        chars = self.failure_characteristics.get("number_of_failures", {})
        if isinstance(chars, dict):
            return randint(
                a=chars.get("lower_bound", 1),
                b=chars.get("upper_bound", 3),
            )
        return 1

    def generate_weibull_lognormal_failure(self, last_available_time: int) -> dict:
        """
        Gera UMA nova falha usando Weibull (TTF) + Lognormal (TTR).
        
        Args:
            last_available_time: Último tempo em que o servidor ficou disponível
        
        Returns:
            dict: Registro de falha no formato padrão
        """
        weibull_params = self.failure_characteristics.get('weibull_ttf_params', {})
        lognormal_params = self.failure_characteristics.get('lognormal_ttr_params', {})
        
        if not weibull_params or not lognormal_params:
            raise ValueError("Parâmetros Weibull/Lognormal não encontrados em failure_characteristics")
        
        # Gerar TTF usando Weibull
        ttf = stats.weibull_min.rvs(
            c=weibull_params['shape'],
            scale=weibull_params['scale'],
            loc=0,
            size=1
        )[0]
        ttf = max(ttf, 1.0)
        
        # Calcular próximo tempo de falha
        failure_starts_at = int(last_available_time + ttf)
        
        # Gerar TTR usando Lognormal
        ttr = stats.lognorm.rvs(
            s=lognormal_params['shape'],
            scale=lognormal_params['scale'],
            loc=0,
            size=1
        )[0]
        ttr = max(ttr, 1.0)
        ttr = min(ttr, 150)  # Limitar máximo
        
        # Calcular timestamps completos
        failure_ends_at = failure_starts_at + int(ttr) - 1
        starts_booting_at = failure_ends_at + 1
        finishes_booting_at = starts_booting_at + self.device.time_to_boot - 1
        becomes_available_at = finishes_booting_at + 1
        
        return {
            "failure_starts_at": failure_starts_at,
            "failure_duration": int(ttr),
            "failure_ends_at": failure_ends_at,
            "starts_booting_at": starts_booting_at,
            "finishes_booting_at": finishes_booting_at,
            "becomes_available_at": becomes_available_at,
        }

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
        pass

    def generate_failure_set(self, next_failure_time_step: int):
        """Gera um grupo de falhas a partir do time step especificado (uniforme)."""
        if next_failure_time_step != float("inf"):
            interval_between_sets_is_infinity = self.failure_characteristics.get("interval_between_sets") == float("inf")
            last_failure_lasts_forever = len(self.failure_trace) > 0 and self.failure_trace[-1][-1].get("failure_duration") == float("inf")

            if len(self.failure_trace) > 0 and (interval_between_sets_is_infinity or last_failure_lasts_forever):
                return

            number_of_failures_within_set = self._sample_number_of_failures()

            # Creating the failure group
            failure_group = []

            # Creating failures that will compose the failure group
            for failure_count in range(number_of_failures_within_set):
                failure = {}

                if failure_count == 0:
                    failure["failure_starts_at"] = next_failure_time_step
                else:
                    if failure_group[-1]["becomes_available_at"] == float("inf"):
                        break
                    if self.failure_characteristics.get("interval_between_failures") == float("inf"):
                        break

                    interval_from_last_failure = self._sample_interval_between_failures()
                    failure["failure_starts_at"] = failure_group[-1]["becomes_available_at"] + interval_from_last_failure + 1

                if self.device.model is not None:
                    if failure["failure_starts_at"] < self.device.model.schedule.steps + 1:
                        failure["failure_starts_at"] = self.device.model.schedule.steps + 2

                if self.failure_characteristics.get("failure_duration") == float("inf"):
                    failure["failure_duration"] = float("inf")
                    failure["failure_ends_at"] = float("inf")
                else:
                    failure["failure_duration"] = self._sample_failure_duration()
                    failure["failure_ends_at"] = failure["failure_starts_at"] + failure["failure_duration"] - 1
                    failure["starts_booting_at"] = failure["failure_ends_at"] + 1
                    failure["finishes_booting_at"] = failure["starts_booting_at"] + self.device.time_to_boot - 1
                    failure["becomes_available_at"] = failure["finishes_booting_at"] + 1

                failure_group.append(failure)

            self.failure_trace.append(failure_group)