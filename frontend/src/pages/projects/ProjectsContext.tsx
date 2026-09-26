import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Project, TimesheetEntry, ProjectExpense, ProjectInvoice } from './types';
import { projectService, type ProjectInvoiceInput } from '../../services/projectService';
import { expenseService } from '../../services/expenseService';
import { timesheetService } from '../../services/timesheetService';
import { tokenStorage, toApiError } from '../../services/apiClient';
import { useToast } from '../../components/common/Toast';

export interface ProjectFormData {
  name: string;
  customerId: string;
  customer: string;
  description: string;
  status: Project['status'];
  startDate: string;
  endDate: string;
  billingMethod: Project['billingMethod'];
  budget: number;
  notes?: string;
}

interface ProjectsContextType {
  projects: Project[];
  loading: boolean;
  refreshProjects: () => Promise<void>;
  getProject: (id: string) => Project | undefined;
  /** Fetches one project's full detail (timesheets, expenses, invoices, payments) into state. */
  loadProject: (id: string) => Promise<Project | undefined>;
  /** Resolves with the saved project (real server id) or null when the save failed. */
  addProject: (data: ProjectFormData) => Promise<Project | null>;
  updateProject: (id: string, updates: Partial<Project>) => Promise<boolean>;
  deleteProject: (id: string) => Promise<boolean>;
  duplicateProject: (id: string) => Promise<Project | null>;
  markAsCompleted: (id: string) => Promise<boolean>;
  addTimesheet: (projectId: string, entry: Omit<TimesheetEntry, 'id' | 'projectId'>) => Promise<boolean>;
  addExpense: (projectId: string, expense: Omit<ProjectExpense, 'id' | 'projectId'>) => Promise<boolean>;
  addInvoice: (projectId: string, invoice: ProjectInvoiceInput) => Promise<ProjectInvoice | null>;
}

const ProjectsContext = createContext<ProjectsContextType | undefined>(undefined);

function errorMessage(err: unknown, fallback: string): string {
  return toApiError(err).message || fallback;
}

export function ProjectsProvider({ children }: { children: React.ReactNode }) {
  const { showToast } = useToast();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  // The list endpoint already carries billed/expense totals; per-project detail is
  // fetched only by the detail page (no N+1 on the list).
  const fetchProjects = useCallback(async () => {
    if (!tokenStorage.hasSession()) {
      setProjects([]);
      setLoading(false);
      return;
    }
    try {
      setLoading(true);
      const data = await projectService.list();
      setProjects((prev) =>
        data.map((p) => {
          // Keep already-loaded detail collections so the detail page does not flash empty.
          const known = prev.find((x) => x.id === p.id);
          return known
            ? {
                ...p,
                timesheets: known.timesheets,
                expenseList: known.expenseList,
                invoices: known.invoices,
                payments: known.payments,
                transactions: known.transactions,
              }
            : p;
        })
      );
    } catch (err) {
      showToast('error', 'Failed to load projects', errorMessage(err, 'Failed to load projects from server.'));
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    if (!tokenStorage.hasSession()) {
      setLoading(false);
      return;
    }
    fetchProjects();
  }, [fetchProjects]);

  const getProject = useCallback((id: string) => projects.find((p) => p.id === id), [projects]);

  const upsert = useCallback((project: Project) => {
    setProjects((prev) =>
      prev.some((p) => p.id === project.id)
        ? prev.map((p) => (p.id === project.id ? project : p))
        : [project, ...prev]
    );
  }, []);

  const loadProject = useCallback(
    async (id: string): Promise<Project | undefined> => {
      try {
        const detail = await projectService.get(id);
        upsert(detail);
        return detail;
      } catch (err) {
        const apiError = toApiError(err);
        if (apiError.status !== 404) {
          showToast('error', 'Failed to load project', errorMessage(err, 'Could not load project details.'));
        }
        return undefined;
      }
    },
    [showToast, upsert]
  );

  const addProject = useCallback(
    async (data: ProjectFormData): Promise<Project | null> => {
      try {
        const created = await projectService.create({
          name: data.name,
          customer_id: data.customerId || undefined,
          customer_name: data.customerId ? undefined : data.customer || undefined,
          description: data.description,
          status: data.status,
          start_date: data.startDate || undefined,
          end_date: data.endDate || undefined,
          billing_method: data.billingMethod,
          budget: data.budget,
          notes: data.notes,
        });
        upsert(created);
        return created;
      } catch (err) {
        showToast('error', 'Failed to save project', errorMessage(err, 'Failed to save project to server.'));
        return null;
      }
    },
    [showToast, upsert]
  );

  const updateProject = useCallback(
    async (id: string, updates: Partial<Project>): Promise<boolean> => {
      const backup = projects.find((p) => p.id === id);
      setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, ...updates } : p)));
      try {
        const saved = await projectService.update(id, {
          name: updates.name,
          customer_id: updates.customerId,
          description: updates.description,
          status: updates.status,
          start_date: updates.startDate,
          end_date: updates.endDate,
          billing_method: updates.billingMethod,
          budget: updates.budget,
          project_manager: updates.projectManager,
          notes: updates.notes,
        });
        setProjects((prev) =>
          prev.map((p) =>
            p.id === id
              ? {
                  ...saved,
                  timesheets: p.timesheets,
                  expenseList: p.expenseList,
                  invoices: p.invoices,
                  payments: p.payments,
                  transactions: p.transactions,
                }
              : p
          )
        );
        return true;
      } catch (err) {
        if (backup) setProjects((prev) => prev.map((p) => (p.id === id ? backup : p)));
        showToast('error', 'Failed to update project', errorMessage(err, 'Failed to update project on server.'));
        return false;
      }
    },
    [projects, showToast]
  );

  const deleteProject = useCallback(
    async (id: string): Promise<boolean> => {
      const backup = projects;
      setProjects((prev) => prev.filter((p) => p.id !== id));
      try {
        await projectService.delete(id);
        return true;
      } catch (err) {
        setProjects(backup);
        showToast('error', 'Failed to delete project', errorMessage(err, 'Failed to delete project from server.'));
        return false;
      }
    },
    [projects, showToast]
  );

  const duplicateProject = useCallback(
    async (id: string): Promise<Project | null> => {
      const source = projects.find((p) => p.id === id);
      if (!source) return null;
      return addProject({
        name: `${source.name} (Copy)`,
        customerId: source.customerId || '',
        customer: source.customer || '',
        description: source.description || '',
        status: 'draft',
        startDate: source.startDate || '',
        endDate: source.endDate || '',
        billingMethod: source.billingMethod || 'fixed_price',
        budget: source.budget || 0,
        notes: source.notes || '',
      });
    },
    [projects, addProject]
  );

  const markAsCompleted = useCallback(
    (id: string) => updateProject(id, { status: 'completed' }),
    [updateProject]
  );

  const addTimesheet = useCallback(
    async (projectId: string, entry: Omit<TimesheetEntry, 'id' | 'projectId'>): Promise<boolean> => {
      const project = projects.find((p) => p.id === projectId);
      try {
        await timesheetService.create({
          project_id: projectId,
          project_name: project?.name,
          // Hours logged on a project bill to the project's customer.
          customer_id: project?.customerId || undefined,
          date: entry.date,
          duration_hours: entry.hours,
          description: entry.description,
          billable: entry.billable,
          billing_rate: entry.hourlyRate,
        });
        await loadProject(projectId);
        return true;
      } catch (err) {
        showToast('error', 'Time entry not saved', errorMessage(err, 'Failed to record the time entry.'));
        return false;
      }
    },
    [projects, loadProject, showToast]
  );

  const addExpense = useCallback(
    async (projectId: string, expense: Omit<ProjectExpense, 'id' | 'projectId'>): Promise<boolean> => {
      const project = projects.find((p) => p.id === projectId);
      try {
        await expenseService.create({
          name: expense.title,
          projectId,
          customerId: project?.customerId || undefined,
          category: expense.category,
          amount: expense.amount,
          date: expense.date,
          billable: expense.billable,
          status: expense.status,
        });
        await loadProject(projectId);
        return true;
      } catch (err) {
        showToast('error', 'Expense not saved', errorMessage(err, 'Failed to record the expense.'));
        return false;
      }
    },
    [projects, loadProject, showToast]
  );

  const addInvoice = useCallback(
    async (projectId: string, invoice: ProjectInvoiceInput): Promise<ProjectInvoice | null> => {
      try {
        const created = await projectService.createInvoice(projectId, invoice);
        await loadProject(projectId);
        return created;
      } catch (err) {
        showToast('error', 'Invoice not created', errorMessage(err, 'Failed to create the project invoice.'));
        return null;
      }
    },
    [loadProject, showToast]
  );

  return (
    <ProjectsContext.Provider
      value={{
        projects,
        loading,
        refreshProjects: fetchProjects,
        getProject,
        loadProject,
        addProject,
        updateProject,
        deleteProject,
        duplicateProject,
        markAsCompleted,
        addTimesheet,
        addExpense,
        addInvoice,
      }}
    >
      {children}
    </ProjectsContext.Provider>
  );
}

export function useProjects() {
  const context = useContext(ProjectsContext);
  if (!context) {
    throw new Error('useProjects must be used within a ProjectsProvider');
  }
  return context;
}
