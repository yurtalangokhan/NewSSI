"use client";

import { useCallback, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import Button from "@/refresh-components/buttons/Button";
import { Input } from "@/components/ui/input";
import Label from "@/refresh-components/form/Label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import Switch from "@/refresh-components/inputs/Switch";
import { Badge } from "@/components/ui/badge";
import { Loader2, Play, AlertCircle, CheckCircle } from "lucide-react";
import { ToolWithCategory } from "@/lib/tools/builtInToolUtils";
import {
  executeBuiltInTool,
  ToolExecuteResponse,
} from "@/lib/tools/mcpService";
import { MailConfig, useMailConfigs } from "@/lib/mailConfigs";
import { toast } from "@/hooks/useToast";
import _ from "lodash";
import { useTranslation } from "react-i18next";

interface ToolPlaygroundProps {
  tool: ToolWithCategory;
  isOpen: boolean;
  onClose: () => void;
}

interface FormValues {
  [key: string]: any;
}

function getSendEmailPlaygroundSchema(mailConfigs: MailConfig[]) {
  const enumLabels = mailConfigs.reduce<Record<string, string>>(
    (labels, config) => {
      labels[config.id] = `${config.name} (${config.from_email})`;
      return labels;
    },
    {}
  );

  return {
    type: "object",
    required: ["mail_config_id", "to", "subject", "body"],
    properties: {
      mail_config_id: {
        type: "string",
        title: "Mail config",
        description: "Select the configured SMTP account to send from.",
        enum: mailConfigs.map((config) => config.id),
        enumLabels,
      },
      to: {
        type: "string",
        title: "To",
        description:
          "Recipient email addresses. Separate multiple addresses with commas.",
      },
      subject: {
        type: "string",
        title: "Subject",
      },
      body: {
        type: "string",
        title: "Body",
      },
      cc: {
        type: "string",
        title: "Cc",
        description: "Optional. Separate multiple addresses with commas.",
      },
      bcc: {
        type: "string",
        title: "Bcc",
        description: "Optional. Separate multiple addresses with commas.",
      },
      is_html: {
        type: "boolean",
        title: "HTML",
        default: false,
      },
      reply_to: {
        type: "string",
        title: "Reply to",
      },
    },
  };
}

function SchemaForm({
  schema,
  values,
  onChange,
}: {
  schema: Record<string, any>;
  values: FormValues;
  onChange: (values: FormValues) => void;
}) {
  const { t } = useTranslation();
  const [formValues, setFormValues] = useState<FormValues>(values || {});

  const handleChange = (name: string, value: any) => {
    const newValues = { ...formValues, [name]: value };
    setFormValues(newValues);
    onChange(newValues);
  };

  if (!schema || !schema.properties) {
    return (
      <div className="text-gray-500">{t("toolPlayground.noInputSchema")}</div>
    );
  }

  return (
    <div className="space-y-4">
      {Object.entries(schema.properties).map(
        ([name, property]: [string, any]) => {
          const isRequired = schema.required?.includes(name);
          const label = property.title || name;
          const description = property.description;

          return (
            <div key={name} className="space-y-2">
              <div className="flex items-center justify-between">
                <Label name={name}>{_.startCase(label)}</Label>
                {isRequired && (
                  <span className="text-xs text-gray-500">
                    {t("toolPlayground.required")}
                  </span>
                )}
              </div>

              {description && (
                <p className="text-xs text-gray-500">{description}</p>
              )}

              {renderField(
                name,
                property,
                formValues[name],
                (value: any) => handleChange(name, value),
                t
              )}
            </div>
          );
        }
      )}
    </div>
  );
}

function renderField(
  name: string,
  property: any,
  value: any,
  onChange: (value: any) => void,
  t: (key: string) => string
) {
  if (property.enum) {
    return (
      <Select value={value || ""} onValueChange={onChange}>
        <SelectTrigger id={name}>
          <SelectValue placeholder={t("toolPlayground.selectOption")} />
        </SelectTrigger>
        <SelectContent>
          {property.enum.map((option: string) => (
            <SelectItem key={option} value={option}>
              {property.enumLabels?.[option] || option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  switch (property.type) {
    case "string":
      return (
        <Input
          id={name}
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={property.example || `Enter ${name}`}
        />
      );

    case "number":
    case "integer":
      if (property.minimum !== undefined && property.maximum !== undefined) {
        return (
          <div className="space-y-2">
            <Slider
              id={name}
              value={[value || property.minimum]}
              min={property.minimum}
              max={property.maximum}
              step={property.type === "integer" ? 1 : 0.1}
              onValueChange={(vals) => onChange(vals[0])}
            />
            <div className="flex justify-between text-xs text-gray-500">
              <span>{property.minimum}</span>
              <span>{value !== undefined ? value : "-"}</span>
              <span>{property.maximum}</span>
            </div>
          </div>
        );
      }

      return (
        <Input
          id={name}
          type="number"
          value={value || ""}
          onChange={(e) => onChange(Number(e.target.value))}
          min={property.minimum}
          max={property.maximum}
          step={property.type === "integer" ? 1 : 0.1}
          placeholder={property.example || `Enter ${name}`}
        />
      );

    case "boolean":
      return (
        <div className="flex items-center space-x-2">
          <Switch id={name} checked={!!value} onCheckedChange={onChange} />
          <Label name={name}>
            {value ? t("toolPlayground.enabled") : t("toolPlayground.disabled")}
          </Label>
        </div>
      );

    default:
      return (
        <Input
          id={name}
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={`Enter ${name}`}
        />
      );
  }
}

function ResponseViewer({
  response,
  isLoading,
  error,
}: {
  response: any;
  isLoading: boolean;
  error: string | null;
}) {
  const { t } = useTranslation();
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="size-6 animate-spin mr-2" />
        <span>{t("toolPlayground.executingTool")}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 p-4 bg-red-50 border border-red-200 rounded-lg">
        <AlertCircle className="size-5 text-red-600 shrink-0 mt-0.5" />
        <div>
          <p className="font-medium text-red-800">
            {t("toolPlayground.error")}
          </p>
          <p className="text-sm text-red-700 mt-1">{error}</p>
        </div>
      </div>
    );
  }

  if (!response) {
    return (
      <div className="text-center py-8 text-gray-500">
        {t("toolPlayground.runToSeeResults")}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-green-700">
        <CheckCircle className="size-4" />
        <span className="font-medium">{t("toolPlayground.result")}</span>
      </div>
      <pre className="bg-gray-100 p-4 rounded-lg overflow-auto text-sm max-h-96">
        {typeof response === "string"
          ? response
          : JSON.stringify(response, null, 2)}
      </pre>
    </div>
  );
}

export default function ToolPlayground({
  tool,
  isOpen,
  onClose,
}: ToolPlaygroundProps) {
  const { t } = useTranslation();
  const { mailConfigs, isLoading: isMailConfigsLoading } = useMailConfigs();
  const [inputValues, setInputValues] = useState<FormValues>({});
  const [response, setResponse] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const inputSchema = useMemo(
    () =>
      tool.name === "send_email"
        ? getSendEmailPlaygroundSchema(mailConfigs)
        : tool.input_schema,
    [tool.name, tool.input_schema, mailConfigs]
  );

  const handleExecute = useCallback(async () => {
    setIsLoading(true);
    setResponse(null);
    setErrorMessage(null);

    try {
      const result: ToolExecuteResponse = await executeBuiltInTool(
        tool.name,
        inputValues
      );

      if (result.error) {
        setErrorMessage(result.error);
        toast.error(result.error);
      } else {
        setResponse(result.result);
        toast.success(t("toolPlayground.executedSuccessfully"));
      }
    } catch (err) {
      const errorMsg =
        err instanceof Error ? err.message : "Tool execution failed";
      setErrorMessage(errorMsg);
      toast.error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  }, [tool.name, inputValues]);

  const handleClose = useCallback(() => {
    setInputValues({});
    setResponse(null);
    setErrorMessage(null);
    onClose();
  }, [onClose]);

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span>{tool.name}</span>
            {tool.category && (
              <Badge variant="secondary">
                {tool.categoryLabel || tool.category}
              </Badge>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            {tool.description || t("toolPlayground.noDescription")}
          </p>

          <div className="border-t pt-4">
            <h3 className="font-medium mb-4">
              {t("toolPlayground.inputHeader")}
            </h3>
            <SchemaForm
              schema={inputSchema}
              values={inputValues}
              onChange={setInputValues}
            />
            {tool.name === "send_email" &&
              !isMailConfigsLoading &&
              mailConfigs.length === 0 && (
                <p className="mt-3 text-xs text-gray-500">
                  {t("toolPlayground.addMailConfigFirst")}
                </p>
              )}
          </div>

          <Button
            onClick={handleExecute}
            disabled={isLoading}
            className="w-full"
          >
            {isLoading ? (
              <>
                <Loader2 className="size-4 animate-spin mr-2" />
                {t("toolPlayground.running")}
              </>
            ) : (
              <>
                <Play className="size-4 mr-2" />
                {t("toolPlayground.runTool")}
              </>
            )}
          </Button>

          <div className="border-t pt-4">
            <h3 className="font-medium mb-4">
              {t("toolPlayground.responseHeader")}
            </h3>
            <ResponseViewer
              response={response}
              isLoading={isLoading}
              error={errorMessage}
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
