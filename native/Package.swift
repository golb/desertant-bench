// swift-tools-version: 6.2
import PackageDescription
let package = Package(
    name: "bench", platforms: [.macOS(.v15)],
    dependencies: [.package(url: "https://github.com/Desert-Ant-Labs/desert-ant-core.git", exact: "4.1.0")],
    targets: [.executableTarget(name: "bench", dependencies: [
        .product(name: "Voz", package: "desert-ant-core"),
        .product(name: "Who", package: "desert-ant-core"),
        .product(name: "Ear", package: "desert-ant-core"),
        .product(name: "Clear", package: "desert-ant-core"),
        .product(name: "Gist", package: "desert-ant-core"),
    ])]
)
