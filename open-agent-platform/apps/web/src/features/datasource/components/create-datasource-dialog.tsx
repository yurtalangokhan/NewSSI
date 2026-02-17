"use client";

import { useState, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import {
    Database,
    Search,
    CheckCircle,
    XCircle,
    Loader2,
    ChevronRight,
    ChevronLeft,
} from "lucide-react";
import { useConnectors, useDataSources, ConnectorInfo, ConnectorSpec, StreamInfo } from "@/hooks/use-datasources";

interface CreateDataSourceDialogProps {
    onCreated?: () => void;
}

type Step = "connector" | "config" | "streams" | "confirm";

export function CreateDataSourceDialog({ onCreated }: CreateDataSourceDialogProps = {}) {
    const [open, setOpen] = useState(false);
    const [step, setStep] = useState<Step>("connector");
    const [loading, setLoading] = useState(false);

    // Connector selection
    const [searchQuery, setSearchQuery] = useState("");
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
    const [selectedConnector, setSelectedConnector] = useState<ConnectorInfo | null>(null);

    // Configuration
    const [connectorSpec, setConnectorSpec] = useState<ConnectorSpec | null>(null);
    const [configValues, setConfigValues] = useState<Record<string, any>>({});
    const [validationResult, setValidationResult] = useState<{ valid: boolean; message: string } | null>(null);
    const [validating, setValidating] = useState(false);

    // Streams
    const [availableStreams, setAvailableStreams] = useState<StreamInfo[]>([]);
    const [selectedStreams, setSelectedStreams] = useState<string[]>([]);
    const [loadingStreams, setLoadingStreams] = useState(false);

    // Final
    const [sourceName, setSourceName] = useState("");

    const { connectors, categories, categoryLabels, byCategory, searchConnectors: _searchConnectors, getConnectorSpec, validateConfig, getStreams } = useConnectors();
    const { createDataSource } = useDataSources();

    // Filtered connectors
    const filteredConnectors = useMemo(() => {
        let result = connectors;

        if (selectedCategory) {
            result = byCategory[selectedCategory] || [];
        }

        if (searchQuery.trim()) {
            const query = searchQuery.toLowerCase();
            result = result.filter(
                c => c.name.toLowerCase().includes(query) ||
                    c.display_name.toLowerCase().includes(query)
            );
        }

        return result;
    }, [connectors, byCategory, selectedCategory, searchQuery]);

    // Reset on close
    useEffect(() => {
        if (!open) {
            setStep("connector");
            setSearchQuery("");
            setSelectedCategory(null);
            setSelectedConnector(null);
            setConnectorSpec(null);
            setConfigValues({});
            setValidationResult(null);
            setAvailableStreams([]);
            setSelectedStreams([]);
            setSourceName("");
        }
    }, [open]);

    // Load spec when connector selected
    useEffect(() => {
        if (selectedConnector && step === "config") {
            loadConnectorSpec();
        }
    }, [selectedConnector, step]);

    async function loadConnectorSpec() {
        if (!selectedConnector) return;
        setLoading(true);
        const spec = await getConnectorSpec(selectedConnector.name);
        setConnectorSpec(spec);
        setLoading(false);
    }

    async function handleValidateConfig() {
        if (!selectedConnector) return;
        setValidating(true);
        setValidationResult(null);
        const result = await validateConfig(selectedConnector.name, configValues);
        setValidationResult(result);
        setValidating(false);
    }

    async function handleLoadStreams() {
        if (!selectedConnector) return;
        setLoadingStreams(true);
        const streams = await getStreams(selectedConnector.name, configValues);
        setAvailableStreams(streams);
        setLoadingStreams(false);
    }

    async function handleCreate() {
        if (!selectedConnector) return;
        setLoading(true);

        const result = await createDataSource(sourceName, {
            connector_type: selectedConnector.name,
            connector_config: configValues,
            streams: selectedStreams.length > 0 ? selectedStreams : undefined,
        });

        setLoading(false);
        if (result) {
            setOpen(false);
            // Trigger refresh in parent component
            onCreated?.();
        }
    }

    function handleNextStep() {
        if (step === "connector" && selectedConnector) {
            setStep("config");
        } else if (step === "config" && validationResult?.valid) {
            setStep("streams");
            handleLoadStreams();
        } else if (step === "streams") {
            setStep("confirm");
            setSourceName(selectedConnector?.display_name || "New Data Source");
        }
    }

    function handlePrevStep() {
        if (step === "config") setStep("connector");
        else if (step === "streams") setStep("config");
        else if (step === "confirm") setStep("streams");
    }

    // Render config field based on JSON Schema
    function renderConfigField(key: string, schema: any) {
        const value = configValues[key] ?? "";
        const isRequired = connectorSpec?.connection_specification?.required?.includes(key);

        // Determine field type
        const type = schema.type;
        const isSecret = schema.airbyte_secret || key.toLowerCase().includes("password") || key.toLowerCase().includes("secret");

        return (
            <div key={key} className="grid gap-2">
                <Label htmlFor={key} className="flex items-center gap-1">
                    {schema.title || key}
                    {isRequired && <span className="text-red-500">*</span>}
                </Label>
                {schema.description && (
                    <p className="text-xs text-muted-foreground">{schema.description}</p>
                )}
                {type === "boolean" ? (
                    <Checkbox
                        id={key}
                        checked={!!value}
                        onCheckedChange={(checked: boolean) => setConfigValues({ ...configValues, [key]: checked })}
                    />
                ) : schema.enum ? (
                    <select
                        id={key}
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={value}
                        onChange={(e) => setConfigValues({ ...configValues, [key]: e.target.value })}
                    >
                        <option value="">Select...</option>
                        {schema.enum.map((opt: string) => (
                            <option key={opt} value={opt}>{opt}</option>
                        ))}
                    </select>
                ) : (
                    <Input
                        id={key}
                        type={isSecret ? "password" : type === "integer" ? "number" : "text"}
                        placeholder={schema.examples?.[0] || ""}
                        value={value}
                        onChange={(e) => setConfigValues({
                            ...configValues,
                            [key]: type === "integer" ? parseInt(e.target.value) || "" : e.target.value
                        })}
                    />
                )}
            </div>
        );
    }

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                    <Database className="h-4 w-4" />
                    Add Data Source
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[700px] max-h-[85vh]">
                <DialogHeader>
                    <DialogTitle>
                        {step === "connector" && "Select Connector"}
                        {step === "config" && `Configure ${selectedConnector?.display_name}`}
                        {step === "streams" && "Select Streams"}
                        {step === "confirm" && "Create Data Source"}
                    </DialogTitle>
                    <DialogDescription>
                        {step === "connector" && "Choose from 600+ available data source connectors."}
                        {step === "config" && "Configure the connection settings for your data source."}
                        {step === "streams" && "Select which data streams to sync."}
                        {step === "confirm" && "Review and create your data source."}
                    </DialogDescription>
                </DialogHeader>

                {/* Step 1: Connector Selection */}
                {step === "connector" && (
                    <div className="space-y-4">
                        <div className="flex gap-2">
                            <div className="relative flex-1">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input
                                    placeholder="Search connectors..."
                                    className="pl-9"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                />
                            </div>
                        </div>

                        <Tabs value={selectedCategory || "all"} onValueChange={(v) => setSelectedCategory(v === "all" ? null : v)}>
                            <TabsList className="flex-wrap h-auto gap-1">
                                <TabsTrigger value="all" className="text-xs">All</TabsTrigger>
                                {categories.map(cat => (
                                    <TabsTrigger key={cat} value={cat} className="text-xs gap-1">
                                        {categoryLabels[cat] || cat.charAt(0).toUpperCase() + cat.slice(1)}
                                    </TabsTrigger>
                                ))}
                            </TabsList>
                        </Tabs>

                        <ScrollArea className="h-[300px] border rounded-md p-2">
                            <div className="grid grid-cols-2 gap-2">
                                {filteredConnectors.map(connector => (
                                    <button
                                        key={connector.name}
                                        className={`p-3 rounded-md border text-left transition-colors ${selectedConnector?.name === connector.name
                                            ? "border-primary bg-primary/10"
                                            : "hover:bg-muted"
                                            }`}
                                        onClick={() => setSelectedConnector(connector)}
                                    >
                                        <div className="font-medium text-sm">{connector.display_name}</div>
                                        <div className="text-xs text-muted-foreground">{connector.name}</div>
                                    </button>
                                ))}
                                {filteredConnectors.length === 0 && (
                                    <div className="col-span-2 text-center py-8 text-muted-foreground">
                                        No connectors found
                                    </div>
                                )}
                            </div>
                        </ScrollArea>
                    </div>
                )}

                {/* Step 2: Configuration */}
                {step === "config" && (
                    <div className="space-y-4">
                        {loading ? (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 className="h-6 w-6 animate-spin" />
                            </div>
                        ) : connectorSpec ? (
                            <>
                                <ScrollArea className="h-[350px] pr-4">
                                    <div className="space-y-4">
                                        {Object.entries(connectorSpec.connection_specification.properties || {}).map(
                                            ([key, schema]: [string, any]) => renderConfigField(key, schema)
                                        )}
                                    </div>
                                </ScrollArea>

                                <div className="flex items-center gap-2">
                                    <Button
                                        variant="outline"
                                        onClick={handleValidateConfig}
                                        disabled={validating}
                                    >
                                        {validating ? (
                                            <Loader2 className="h-4 w-4 animate-spin mr-2" />
                                        ) : null}
                                        Test Connection
                                    </Button>
                                    {validationResult && (
                                        <div className={`flex items-center gap-1 text-sm ${validationResult.valid ? "text-green-600" : "text-red-600"}`}>
                                            {validationResult.valid ? (
                                                <CheckCircle className="h-4 w-4" />
                                            ) : (
                                                <XCircle className="h-4 w-4" />
                                            )}
                                            {validationResult.message}
                                        </div>
                                    )}
                                </div>
                            </>
                        ) : (
                            <div className="text-center py-8 text-muted-foreground">
                                Failed to load connector configuration
                            </div>
                        )}
                    </div>
                )}

                {/* Step 3: Stream Selection */}
                {step === "streams" && (
                    <div className="space-y-4">
                        {loadingStreams ? (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 className="h-6 w-6 animate-spin" />
                                <span className="ml-2">Discovering available streams...</span>
                            </div>
                        ) : (
                            <>
                                <div className="flex items-center justify-between">
                                    <p className="text-sm text-muted-foreground">
                                        {selectedStreams.length === 0
                                            ? "All streams will be synced"
                                            : `${selectedStreams.length} streams selected`}
                                    </p>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => setSelectedStreams(
                                            selectedStreams.length === availableStreams.length
                                                ? []
                                                : availableStreams.map(s => s.name)
                                        )}
                                    >
                                        {selectedStreams.length === availableStreams.length ? "Deselect All" : "Select All"}
                                    </Button>
                                </div>

                                <ScrollArea className="h-[300px] border rounded-md p-2">
                                    <div className="space-y-2">
                                        {availableStreams.map(stream => (
                                            <label
                                                key={stream.name}
                                                className="flex items-center gap-2 p-2 rounded hover:bg-muted cursor-pointer"
                                            >
                                                <Checkbox
                                                    checked={selectedStreams.includes(stream.name)}
                                                    onCheckedChange={(checked: boolean) => {
                                                        if (checked) {
                                                            setSelectedStreams([...selectedStreams, stream.name]);
                                                        } else {
                                                            setSelectedStreams(selectedStreams.filter(s => s !== stream.name));
                                                        }
                                                    }}
                                                />
                                                <span className="text-sm">{stream.name}</span>
                                            </label>
                                        ))}
                                        {availableStreams.length === 0 && (
                                            <div className="text-center py-8 text-muted-foreground">
                                                No streams available or could not discover streams.
                                                <br />
                                                <span className="text-xs">All data will be synced.</span>
                                            </div>
                                        )}
                                    </div>
                                </ScrollArea>
                            </>
                        )}
                    </div>
                )}

                {/* Step 4: Confirm */}
                {step === "confirm" && (
                    <div className="space-y-4">
                        <div className="grid gap-4">
                            <div className="grid gap-2">
                                <Label htmlFor="sourceName">Data Source Name</Label>
                                <Input
                                    id="sourceName"
                                    value={sourceName}
                                    onChange={(e) => setSourceName(e.target.value)}
                                    placeholder="Enter a name for this data source"
                                />
                            </div>

                            <div className="rounded-md border p-4 space-y-2">
                                <div className="flex items-center gap-2">
                                    <Badge variant="outline">{selectedConnector?.display_name}</Badge>
                                </div>
                                <div className="text-sm text-muted-foreground">
                                    {selectedStreams.length > 0
                                        ? `${selectedStreams.length} streams selected`
                                        : "All streams will be synced"}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                <DialogFooter className="flex justify-between">
                    <div>
                        {step !== "connector" && (
                            <Button variant="outline" onClick={handlePrevStep}>
                                <ChevronLeft className="h-4 w-4 mr-1" />
                                Back
                            </Button>
                        )}
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline" onClick={() => setOpen(false)}>
                            Cancel
                        </Button>
                        {step === "confirm" ? (
                            <Button onClick={handleCreate} disabled={loading || !sourceName.trim()}>
                                {loading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                                Create Data Source
                            </Button>
                        ) : (
                            <Button
                                onClick={handleNextStep}
                                disabled={
                                    (step === "connector" && !selectedConnector) ||
                                    (step === "config" && !validationResult?.valid)
                                }
                            >
                                Next
                                <ChevronRight className="h-4 w-4 ml-1" />
                            </Button>
                        )}
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
