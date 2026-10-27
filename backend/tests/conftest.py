import pytest


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Les compteurs vivent dans le processus : sans remise a zero, un test
    deborderait sur le suivant.

    L'import reste dans le corps : importer `app` au chargement de ce fichier
    figerait le moteur sur la base par defaut, avant que chaque module n'ait
    pose son propre DATABASE_URL.
    """
    from app.security import reset_rate_limits

    reset_rate_limits()
    yield
    reset_rate_limits()
