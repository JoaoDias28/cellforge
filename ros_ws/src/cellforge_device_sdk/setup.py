from setuptools import find_packages, setup

package_name = "cellforge_device_sdk"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=False,
    maintainer="CellForge Engineering",
    maintainer_email="engineering@example.invalid",
    description=(
        "Vendor-neutral lifecycle, result, and contract-test helpers for CellForge adapters."
    ),
    license="Proprietary",
    tests_require=["pytest"],
)
