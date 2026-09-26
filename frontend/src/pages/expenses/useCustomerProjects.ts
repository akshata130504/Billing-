import { useQuery } from '@tanstack/react-query';
import { projectService } from '../../services/projectService';

export interface ProjectOption {
  id: string;
  name: string;
}

/** Real projects of one customer (server-filtered), for the expense forms' project picker. */
export function useCustomerProjects(customerId: string | undefined) {
  const query = useQuery({
    queryKey: ['projects', 'by-customer', customerId],
    queryFn: () => projectService.list({ customer_id: customerId }),
    enabled: Boolean(customerId),
    staleTime: 30_000,
  });
  const options: ProjectOption[] = (query.data ?? []).map((p) => ({ id: p.id, name: p.name }));
  return { projects: options, loading: query.isLoading && Boolean(customerId), error: query.error };
}
