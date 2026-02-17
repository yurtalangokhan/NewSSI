import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";

// ============================================================================
// Types
// ============================================================================

export interface ConnectorInfo {
    name: string;
    display_name: string;
    category?: string;
}

export interface ConnectorSpec {
    name: string;
    display_name: string;
    connection_specification: Record<string, any>;
    documentation_url?: string;
}

export interface StreamInfo {
    name: string;
}

export interface AirbyteConnectorConfig {
    connector_type: string;
    connector_config: Record<string, any>;
    streams?: string[];
    content_fields?: string[];
}

export interface DataSource {
    id: string;
    name: string;
    connector_type: string;
    connector_display_name: string;
    streams?: string[];
    sync_status?: string;
    sync_progress?: number;
    document_count: number;
    created_at?: string;
    last_synced_at?: string;
}

export interface DataSourceDetails extends DataSource {
    config: Record<string, any>;
    available_streams?: string[];
    sample_documents: Array<{ content: string; metadata: Record<string, any> }>;
    last_error?: string;
}

export interface ConnectorCategory {
    name: string;
    connectors: ConnectorInfo[];
}

// ============================================================================
// API Helper
// ============================================================================

function getApiUrl(): string {
    const url = process.env.NEXT_PUBLIC_AGENT_API_URL;
    if (!url) {
        console.warn("NEXT_PUBLIC_AGENT_API_URL not set, falling back to http://localhost:8123");
        return "http://localhost:8123";
    }
    return url;
}

// ============================================================================
// Connector Hooks
// ============================================================================

export function useConnectors() {
    const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
    const [categories, setCategories] = useState<string[]>([]);
    const [categoryLabels, setCategoryLabels] = useState<Record<string, string>>({});
    const [byCategory, setByCategory] = useState<Record<string, ConnectorInfo[]>>({});
    const [loading, setLoading] = useState(true);

    const fetchConnectors = useCallback(async () => {
        try {
            const res = await fetch(`${getApiUrl()}/datasources/connectors`);
            if (!res.ok) throw new Error("Failed to fetch connectors");
            const data = await res.json();

            setCategories(data.categories || []);
            setCategoryLabels(data.category_labels || {});
            setByCategory(data.by_category || {});

            // Flatten all connectors
            const all: ConnectorInfo[] = [];
            Object.values(data.by_category || {}).forEach((catConnectors: any) => {
                all.push(...catConnectors);
            });
            setConnectors(all);
        } catch (error) {
            console.error(error);
            setConnectors([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchConnectors();
    }, [fetchConnectors]);

    const searchConnectors = useCallback(async (query: string): Promise<ConnectorInfo[]> => {
        if (!query.trim()) return connectors;

        try {
            const res = await fetch(`${getApiUrl()}/datasources/connectors?search=${encodeURIComponent(query)}`);
            if (!res.ok) throw new Error("Search failed");
            const data = await res.json();
            return data.connectors || [];
        } catch {
            // Fallback to client-side filter
            return connectors.filter(
                c => c.name.toLowerCase().includes(query.toLowerCase()) ||
                    c.display_name.toLowerCase().includes(query.toLowerCase())
            );
        }
    }, [connectors]);

    const getConnectorSpec = useCallback(async (connectorName: string): Promise<ConnectorSpec | null> => {
        try {
            const res = await fetch(`${getApiUrl()}/datasources/connectors/${connectorName}/spec`);
            if (!res.ok) throw new Error("Failed to fetch spec");
            return await res.json();
        } catch (error) {
            console.error(error);
            toast.error("Failed to load connector configuration");
            return null;
        }
    }, []);

    const validateConfig = useCallback(async (
        connectorName: string,
        config: Record<string, any>
    ): Promise<{ valid: boolean; message: string }> => {
        try {
            const res = await fetch(`${getApiUrl()}/datasources/connectors/${connectorName}/validate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(config),
            });
            return await res.json();
        } catch (_error) {
            return { valid: false, message: "Connection test failed" };
        }
    }, []);

    const getStreams = useCallback(async (
        connectorName: string,
        config: Record<string, any>
    ): Promise<StreamInfo[]> => {
        try {
            const res = await fetch(`${getApiUrl()}/datasources/connectors/${connectorName}/streams`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(config),
            });
            if (!res.ok) throw new Error("Failed to get streams");
            return await res.json();
        } catch (error) {
            console.error(error);
            return [];
        }
    }, []);

    return {
        connectors,
        categories,
        categoryLabels,
        byCategory,
        loading,
        searchConnectors,
        getConnectorSpec,
        validateConfig,
        getStreams,
        refresh: fetchConnectors,
    };
}

// ============================================================================
// Data Source Hooks
// ============================================================================

export function useDataSources() {
    const [dataSources, setDataSources] = useState<DataSource[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchDataSources = useCallback(async () => {
        try {
            const res = await fetch(`${getApiUrl()}/datasources`);
            if (res.status === 503) {
                setDataSources([]);
                return;
            }
            if (!res.ok) throw new Error("Failed to fetch data sources");
            const data = await res.json();
            setDataSources(data);
        } catch (error) {
            console.error(error);
            setDataSources([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchDataSources();
    }, [fetchDataSources]);

    const createDataSource = async (
        name: string,
        config: AirbyteConnectorConfig
    ): Promise<DataSource | null> => {
        try {
            const res = await fetch(`${getApiUrl()}/datasources`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, config }),
            });
            if (!res.ok) {
                const error = await res.json();
                throw new Error(error.detail || "Failed to create data source");
            }
            const newSource = await res.json();
            setDataSources((prev) => [...prev, newSource]);
            toast.success("Data source created successfully");
            return newSource;
        } catch (error: any) {
            console.error(error);
            toast.error(error.message || "Failed to create data source");
            return null;
        }
    };

    const syncDataSource = async (id: string) => {
        try {
            const res = await fetch(`${getApiUrl()}/datasources/${id}/sync`, {
                method: "POST",
            });
            if (!res.ok) throw new Error("Failed to start sync");
            toast.success("Sync started");
            setTimeout(() => fetchDataSources(), 2000);
        } catch (error) {
            console.error(error);
            toast.error("Failed to sync data source");
        }
    };

    const deleteDataSource = async (id: string) => {
        try {
            const res = await fetch(`${getApiUrl()}/datasources/${id}`, {
                method: "DELETE",
            });
            if (!res.ok) throw new Error("Failed to delete data source");
            setDataSources((prev) => prev.filter((ds) => ds.id !== id));
            toast.success("Data source deleted");
        } catch (error) {
            console.error(error);
            toast.error("Failed to delete data source");
        }
    };

    const getDataSourceDetails = async (id: string, page: number = 1, pageSize: number = 10): Promise<DataSourceDetails | null> => {
        try {
            const res = await fetch(`${getApiUrl()}/datasources/${id}/details?page=${page}&page_size=${pageSize}`);
            if (!res.ok) throw new Error("Failed to fetch details");
            return await res.json();
        } catch (error) {
            console.error(error);
            toast.error("Failed to load data source details");
            return null;
        }
    };

    const getSyncStatus = async (id: string) => {
        try {
            const res = await fetch(`${getApiUrl()}/datasources/${id}/status`);
            if (!res.ok) return null;
            return await res.json();
        } catch {
            return null;
        }
    };

    return {
        dataSources,
        loading,
        createDataSource,
        syncDataSource,
        deleteDataSource,
        getDataSourceDetails,
        getSyncStatus,
        refresh: fetchDataSources,
    };
}
