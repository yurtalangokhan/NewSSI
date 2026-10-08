interface PreviewBodyProps {
  children: React.ReactNode;
}

/** The scrolling content area of a result preview. */
export default function PreviewBody({ children }: PreviewBodyProps) {
  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-4 py-4">
      {children}
    </div>
  );
}
