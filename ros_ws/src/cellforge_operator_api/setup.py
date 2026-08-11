from setuptools import find_packages, setup

package_name = "cellforge_operator_api"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=[
        "setuptools",
        "fastapi>=0.100,<1",
        "uvicorn>=0.23,<1",
    ],
    zip_safe=False,
    maintainer="CellForge Engineering",
    maintainer_email="engineering@example.invalid",
    description="Offline local operator API, UI, authorization, and audit service.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={"console_scripts": ["operator_api = cellforge_operator_api.main:main"]},
)
