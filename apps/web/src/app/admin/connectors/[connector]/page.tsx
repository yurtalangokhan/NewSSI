import AirbyteConnectorPage from "./AirbyteConnectorPage";

export default async function Page(props: {
  params: Promise<{ connector: string }>;
}) {
  const params = await props.params;
  return <AirbyteConnectorPage connectorName={params.connector} />;
}
