from setuptools import find_packages, setup

package_name = "cellforge_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", ["launch/integrated_runtime.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=False,
    maintainer="CellForge Engineering",
    maintainer_email="engineering@example.invalid",
    description="Immutable offline integrated runtime bringup for CellForge.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={"console_scripts": ["runtime_coordinator = cellforge_bringup.coordinator:main"]},
)
