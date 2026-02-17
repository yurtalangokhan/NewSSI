import { Deployment } from "@/types/deployment";

/**
 * Loads the provided deployments from the environment variable.
 * @returns {Deployment[]} The list of deployments.
 */
export function getDeployments(): Deployment[] {
  let defaultExists = false;
  const deployments: Deployment[] = JSON.parse(
    process.env.NEXT_PUBLIC_DEPLOYMENTS || "[]",
  );

  // Fix Docker networking: When running on the server side (in Docker),
  // localhost refers to the container itself, not the host services.
  // We need to rewrite localhost URLs to use internal Docker service names.
  if (typeof window === "undefined") {
    for (const deployment of deployments) {
      // Rewrite agent-service URL: localhost:8123 -> agent-service:8080
      if (deployment.deploymentUrl.includes("localhost:8123")) {
        deployment.deploymentUrl = deployment.deploymentUrl.replace(
          "localhost:8123",
          "agent-service:8080",
        );
      }
    }
  }
  for (const deployment of deployments) {
    if (deployment.isDefault && !defaultExists) {
      if (!deployment.defaultGraphId) {
        throw new Error("Default deployment must have a default graph ID");
      }
      defaultExists = true;
    } else if (deployment.isDefault && defaultExists) {
      throw new Error("Multiple default deployments found");
    }
  }
  if (!defaultExists) {
    throw new Error("No default deployment found");
  }
  return deployments;
}
