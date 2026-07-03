# Versionado de FutonHUB

FutonHUB utiliza Versionado Semántico:

MAJOR.MINOR.PATCH

Mientras el proyecto permanezca por debajo de 1.0.0:

- PATCH: correcciones compatibles, sin nueva funcionalidad relevante.
- MINOR: nuevos cortes funcionales, mejoras relevantes o cambios controlados de comportamiento.
- 1.0.0: primera versión estable considerada plenamente productiva.

Cada versión publicada debe incluir:

1. versión actualizada en pyproject.toml;
2. __version__ sincronizado;
3. entrada en CHANGELOG.md;
4. commit de release;
5. tag anotado vX.Y.Z;
6. tests aprobados;
7. smoke manual aprobado cuando corresponda.

El hash del commit se conserva como trazabilidad técnica, pero la referencia principal para el equipo será la versión y su tag.
