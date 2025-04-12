def application_step(self):
    """Method that executes the events involving the object at each time step."""
    if not hasattr(self, "availability_history"):
        self.availability_history = []

    # Collecting the application's availability in the current step
    self.availability_history.append(self.availability_status)

    # Updating the current perceived downtime of all users that access the application
    for user in self.users:
        if not hasattr(user, "user_perceived_downtime_history"):
            user.user_perceived_downtime_history = {f"{self.id}": []}

        if user.making_requests[str(self.id)][str(self.model.schedule.steps + 1)]:
            user.user_perceived_downtime_history[f"{self.id}"].append(not self.availability_status)


@property
def availability_status(self):
    for service in self.services:
        if service._available is False:
            return False

    return True
