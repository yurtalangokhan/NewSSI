// CsvContent
import React, { useState, useEffect } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ContentComponentProps } from "./ExpandableContentWrapper";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import { SvgAlertCircle } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

const CsvContent: React.FC<ContentComponentProps> = ({
  fileDescriptor,
  isLoading,
  fadeIn,
  expanded = false,
}) => {
  const { t } = useTranslation();
  const [data, setData] = useState<Record<string, string>[]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [isFetching, setIsFetching] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Cache parsed CSV across mounts so closing other modals doesn't force a refetch.
  // Keyed by file id; safe because chat file ids are unique.
  const cacheKey = fileDescriptor.id;
  const cached = csvCache.get(cacheKey);

  useEffect(() => {
    if (cached) {
      setHeaders(cached.headers);
      setData(cached.data);
      setIsFetching(false);
      setErrorMessage(null);
      return;
    }

    fetchCSV(fileDescriptor.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileDescriptor.id]);

  const fetchCSV = async (id: string) => {
    setIsFetching(true);
    setErrorMessage(null);
    try {
      const response = await fetch(`/api/chat/file/${id}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        setData([]);
        setHeaders([]);
        setErrorMessage(t("filePreview.csvNoLongerInMemory"));
        return;
      }

      const contentLength = response.headers.get("Content-Length");
      const fileSizeInMB = contentLength
        ? parseInt(contentLength) / (1024 * 1024)
        : 0;
      const MAX_FILE_SIZE_MB = 5;

      if (fileSizeInMB > MAX_FILE_SIZE_MB) {
        setData([]);
        setHeaders([]);
        setErrorMessage(
          t("filePreview.csvFileSizeExceeded", { size: MAX_FILE_SIZE_MB })
        );
        return;
      }

      const csvData = await response.text();
      const rows = csvData.trim().split("\n");
      const firstRow = rows[0];
      if (!firstRow) {
        setData([]);
        setHeaders([]);
        setErrorMessage(t("filePreview.csvEmpty"));
        return;
      }
      const parsedHeaders = firstRow.split(",");
      setHeaders(parsedHeaders);

      const parsedData: Record<string, string>[] = rows.slice(1).map((row) => {
        const values = row.split(",");
        return parsedHeaders.reduce<Record<string, string>>(
          (obj, header, index) => {
            const val = values[index];
            if (val !== undefined) {
              obj[header] = val;
            }
            return obj;
          },
          {}
        );
      });
      setData(parsedData);
      csvCache.set(id, { headers: parsedHeaders, data: parsedData });
    } catch (error) {
      console.error("Error fetching CSV file:", error);
      setData([]);
      setHeaders([]);
      setErrorMessage(t("filePreview.csvLoadFailed"));
    } finally {
      setIsFetching(false);
    }
  };

  if (isLoading || isFetching) {
    return (
      <div className="flex items-center justify-center h-[300px]">
        <SimpleLoader />
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex relative overflow-auto",
        expanded ? "max-h-[600px]" : "max-h-[300px]"
      )}
    >
      <Table>
        <TableHeader className="sticky top-0 z-sticky">
          <TableRow className="bg-background-tint-01">
            {headers.map((header, index) => (
              <TableHead key={index}>
                <Text
                  as="p"
                  className="line-clamp-2 font-medium"
                  text03
                  mainUiBody
                >
                  {header}
                </Text>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>

        <TableBody>
          {data.length > 0 ? (
            data.map((row, rowIndex) => (
              <TableRow key={rowIndex}>
                {headers.map((header, cellIndex) => (
                  <TableCell
                    className={cn(
                      cellIndex === 0 && "sticky left-0 bg-background-tint-01",
                      "py-0 px-4"
                    )}
                    key={cellIndex}
                  >
                    {row[header]}
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={headers.length} className="text-center py-8">
                <div className="flex flex-col items-center justify-center space-y-2">
                  <SvgAlertCircle className="w-8 h-8 stroke-error" />
                  <Text as="p" text03 mainUiBody>
                    {headers.length === 0
                      ? t("filePreview.errorLoadingCsv")
                      : t("filePreview.noDataAvailable")}
                  </Text>
                  <Text as="p" text04 mainUiBody>
                    {headers.length === 0
                      ? errorMessage ||
                        t("filePreview.csvMayBeTooLarge")
                      : ""}
                  </Text>
                </div>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
};

export default CsvContent;

const csvCache = new Map<
  string,
  { headers: string[]; data: Record<string, string>[] }
>();
