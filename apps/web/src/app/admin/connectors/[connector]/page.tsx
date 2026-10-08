import ConnectorSetupPage from "./ConnectorSetupPage";

export default async function Page(props: {
  params: Promise<{ connector: string }>;
}) {
  const params = await props.params;
  return <ConnectorSetupPage connectorName={params.connector} />;
}
