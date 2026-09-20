from django.db import models


class Customer(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20,
        choices=[("prospect", "Prospect"), ("customer", "Customer")],
    )
    created_at = models.DateField()

    def __str__(self):
        return f"{self.name} ({self.id})"


class Contact(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=200)
    email = models.CharField(max_length=200)
    role = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} ({self.role})"


class Interaction(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="interactions")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="interactions")
    type = models.CharField(
        max_length=20,
        choices=[
            ("email", "Email"),
            ("call", "Call"),
            ("meeting", "Meeting"),
            ("note", "Note"),
        ],
    )
    occurred_at = models.DateField()
    notes = models.TextField()

    class Meta:
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.type} @ {self.occurred_at} — {self.customer_id}"


class AccountAction(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name="action")
    done = models.BooleanField(default=False)
    snoozed_until = models.DateField(null=True, blank=True)
    pinned = models.BooleanField(default=False)
    kept_open = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"actions({self.customer_id}) done={self.done} pinned={self.pinned}"


class RankingRun(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField()
    stale = models.BooleanField(default=True)

    def __str__(self):
        return f"RankingRun {self.created_at} stale={self.stale}"


class EmailOtp(models.Model):
    """One login code per request; codes are stored hashed, single active per email."""
    email = models.EmailField(db_index=True)
    salt = models.CharField(max_length=32)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed = models.BooleanField(default=False)

    def __str__(self):
        return f"EmailOtp {self.email} consumed={self.consumed}"


class ApiSession(models.Model):
    """Cookie-carried login session; only the token hash is stored."""
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"ApiSession {self.email}"
