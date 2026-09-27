from dataclasses import dataclass
from decimal import Decimal

from faker import Faker

SEED = 42


@dataclass
class Employee:
    employee_id: str
    name: str
    ssn: str
    annual_salary: Decimal


def generate_employees(count: int = 20, seed: int = SEED) -> list[Employee]:
    fake = Faker()
    fake.seed_instance(seed)

    employees = []
    for i in range(1, count + 1):
        salary = fake.random_int(min=45_000, max=150_000, step=500)
        employees.append(
            Employee(
                employee_id=f"E{i:03d}",
                name=fake.name(),
                ssn=fake.ssn(),
                annual_salary=Decimal(salary),
            )
        )
    return employees


if __name__ == "__main__":
    for e in generate_employees():
        print(e)
