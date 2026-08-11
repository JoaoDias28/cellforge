from setuptools import find_packages, setup

package_name = "cellforge_job_gateway"

setup(
    name=package_name,
    version="0.2.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools", "PyYAML>=6,<7"],
    zip_safe=False,
    maintainer="CellForge Engineering",
    maintainer_email="engineering@example.invalid",
    description="Durable job admission, recipe freeze, and supervisor gateway for CellForge.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={"console_scripts": ["job_gateway = cellforge_job_gateway.node:main"]},
)
