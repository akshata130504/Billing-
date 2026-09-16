import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Project, TimesheetEntry, ProjectExpense, ProjectInvoice, ProjectTransaction } from './types';
import { projectService } from '../../services/projectService';
import { expenseService } from '../../services/expenseService';
import { timesheetService } from '../../services/timesheetService';
import { useToast } from '../../components/common/Toast';

interface ProjectsContextType {
  projects: Project[];
  loading: boolean;
  refreshProjects: () => Promise<void>;
  getProject: (id: string) => Project | undefined;
  addProject: (data: {
    name: string;
    customer: string;
    description: string;
    status: Project['status'];
    startDate: string;
    endDate: string;
    billingMethod: Project['billingMethod'];
    budget: number;
    notes?: string;
  }) => Project;
  updateProject: (id: string, updates: Partial<Project>) => void;
  deleteProject: (id: string) => void;
  duplicateProject: (id: string) => Project;
  markAsCompleted: (id: string) => void;
  addTimesheet: (projectId: string, entry: Omit<TimesheetEntry, 'id' | 'projectId'>) => void;
  addExpense: (projectId: string, expense: Omit<ProjectExpense, 'id' | 'projectId'>) => void;
  addInvoice: (projectId: string, invoice: Omit<ProjectInvoice, 'id' | 'projectId'>) => void;
}

const ProjectsContext = createContext<ProjectsContextType | undefined>(undefined);

export function ProjectsProvider({ children }: { children: React.ReactNode }) {
  const { showToast } = useToast();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchProjects = useCallback(async () => {
    try {
      setLoading(true);
      const data = await projectService.list();
      // Fetch full details for each project to populate timesheets and expenses
      const detailed = await Promise.all(
        data.map(async (p) => {
          try {
            return await projectService.get(p.id);
          } catch {
            return p;
          }
        })
      );
      setProjects(detailed);
    } catch (err) {
      console.error('Failed to load projects from backend API:', err);
      showToast('error', 'Failed to load projects from server.');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const getProject = (id: string) => projects.find((p) => p.id === id);

  const addProject = (data: {
    name: string;
    customer: string;
    description: string;
    status: Project['status'];
    startDate: string;
    endDate: string;
    billingMethod: Project['billingMethod'];
    budget: number;
    notes?: string;
  }): Project => {
    // Generate temporary ID for optimistic UI
    const tempId = `PRJ-${Date.now()}`;
    const newProject: Project = {
      id: tempId,
      ...data,
      billed: 0,
      expenses: 0,
      projectManager: '',
      timesheets: [],
      expenseList: [],
      invoices: [],
      payments: [],
      transactions: [],
    };

    setProjects((prev) => [newProject, ...prev]);

    // Asynchronously save to backend
    projectService
      .create({
        name: data.name,
        customer_name: data.customer,
        description: data.description,
        status: data.status,
        start_date: data.startDate || undefined,
        end_date: data.endDate || undefined,
        billing_method: data.billingMethod,
        budget: data.budget,
        notes: data.notes,
      })
      .then((created) => {
        setProjects((prev) =>
          prev.map((p) => (p.id === tempId ? { ...p, id: created.id } : p))
        );
        showToast('success', `Project "${data.name}" created successfully.`);
      })
      .catch((err) => {
        console.error('Failed to create project on backend:', err);
        setProjects((prev) => prev.filter((p) => p.id !== tempId));
        showToast('error', 'Failed to save project to server.');
      });

    return newProject;
  };

  const updateProject = (id: string, updates: Partial<Project>) => {
    setProjects((prev) =>
      prev.map((p) => (p.id === id ? { ...p, ...updates } : p))
    );

    projectService
      .update(id, {
        name: updates.name,
        customer_name: updates.customer,
        description: updates.description,
        status: updates.status,
        start_date: updates.startDate,
        end_date: updates.endDate,
        billing_method: updates.billingMethod,
        budget: updates.budget,
        project_manager: updates.projectManager,
        notes: updates.notes,
      })
      .catch((err) => {
        console.error('Failed to update project on backend:', err);
        showToast('error', 'Failed to update project on server.');
      });
  };

  const deleteProject = (id: string) => {
    const backup = projects;
    setProjects((prev) => prev.filter((p) => p.id !== id));

    projectService
      .delete(id)
      .then(() => {
        showToast('success', 'Project deleted successfully.');
      })
      .catch((err) => {
        console.error('Failed to delete project on backend:', err);
        setProjects(backup);
        showToast('error', 'Failed to delete project from server.');
      });
  };

  const duplicateProject = (id: string): Project => {
    const source = projects.find((p) => p.id === id);
    const newName = `${source ? source.name : 'New Project'} (Copy)`;
    return addProject({
      name: newName,
      customer: source?.customer || '',
      description: source?.description || '',
      status: 'draft',
      startDate: source?.startDate || '',
      endDate: source?.endDate || '',
      billingMethod: source?.billingMethod || 'fixed_price',
      budget: source?.budget || 0,
      notes: source?.notes || '',
    });
  };

  const markAsCompleted = (id: string) => {
    updateProject(id, { status: 'completed' });
  };

  const addTimesheet = (
    projectId: string,
    entry: Omit<TimesheetEntry, 'id' | 'projectId'>
  ) => {
    const tempId = `TS-${Date.now()}`;
    const newEntry: TimesheetEntry = {
      id: tempId,
      projectId,
      ...entry,
    };

    setProjects((prev) =>
      prev.map((p) => {
        if (p.id !== projectId) return p;
        return {
          ...p,
          timesheets: [newEntry, ...(p.timesheets || [])],
        };
      })
    );

    timesheetService
      .create({
        project_id: projectId,
        date: entry.date,
        duration_hours: entry.hours,
        description: entry.description,
        billable: entry.billable,
        billing_rate: entry.hourlyRate,
      })
      .then(() => {
        showToast('success', 'Time entry recorded.');
      })
      .catch((err) => {
        console.error('Failed to persist timesheet on backend:', err);
      });
  };

  const addExpense = (
    projectId: string,
    expense: Omit<ProjectExpense, 'id' | 'projectId'>
  ) => {
    const tempId = `EXP-${Date.now()}`;
    const newExp: ProjectExpense = {
      id: tempId,
      projectId,
      ...expense,
    };

    setProjects((prev) =>
      prev.map((p) => {
        if (p.id !== projectId) return p;
        return {
          ...p,
          expenses: p.expenses + expense.amount,
          expenseList: [newExp, ...(p.expenseList || [])],
        };
      })
    );

    expenseService
      .create({
        name: expense.title,
        project_id: projectId,
        category: expense.category,
        amount: expense.amount,
        date: expense.date,
        billable: expense.billable,
        status: expense.status,
      })
      .then(() => {
        showToast('success', 'Expense recorded for project.');
      })
      .catch((err) => {
        console.error('Failed to persist expense on backend:', err);
      });
  };

  const addInvoice = (
    projectId: string,
    invoice: Omit<ProjectInvoice, 'id' | 'projectId'>
  ) => {
    setProjects((prev) =>
      prev.map((p) => {
        if (p.id !== projectId) return p;
        const invNumber = invoice.invoiceNumber || `INV-${Date.now().toString().slice(-4)}`;
        const newInv: ProjectInvoice = {
          id: invNumber,
          projectId,
          ...invoice,
          invoiceNumber: invNumber,
        };
        const newTxn: ProjectTransaction = {
          id: `TXN-${Date.now().toString().slice(-4)}`,
          projectId,
          type: 'Invoice',
          reference: invNumber,
          date: invoice.date,
          amount: invoice.amount,
          status: invoice.status === 'paid' ? 'Paid' : invoice.status === 'draft' ? 'Draft' : 'Sent',
        };
        return {
          ...p,
          billed: p.billed + invoice.amount,
          invoices: [newInv, ...(p.invoices || [])],
          transactions: [newTxn, ...(p.transactions || [])],
        };
      })
    );
  };

  return (
    <ProjectsContext.Provider
      value={{
        projects,
        loading,
        refreshProjects: fetchProjects,
        getProject,
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
