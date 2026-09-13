from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is Required")

        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)

        user.set_password(password)
        user.save(using=self.db)
        return user

    def create_superuser(self, email, password=None):
        from .models import AccountStatus, UserRole

        if not password:
            raise ValueError("A superuser must have a password.")

        user = self.create_user(
            email=self.normalize_email(email).lower(),
            password=password,
        )

        user.is_admin = True
        user.is_staff = True
        user.is_active = True
        user.is_superadmin = True
        user.role = UserRole.ADMIN
        user.status = AccountStatus.ACTIVE
        user.save(using=self._db)
        return user
