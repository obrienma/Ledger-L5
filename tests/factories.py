import factory

from app.models import Customer


class CustomerFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Customer
        sqlalchemy_session_persistence = "flush"

    name = factory.Faker("company")
    email = factory.Faker("email")
