import HttpErrorPage from "@/components/errorPages/HttpErrorPage";

export default function NotFound() {
  return <HttpErrorPage code={404} />;
}
