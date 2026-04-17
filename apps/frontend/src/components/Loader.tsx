interface LoaderProps {
  label?: string;
}

export const Loader = ({ label = "Loading" }: LoaderProps) => {
  return <div className="loading">{label}…</div>;
};
