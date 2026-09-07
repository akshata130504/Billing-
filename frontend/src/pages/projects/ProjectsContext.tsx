import React, { createContext, useContext, useState, useEffect } from 'react';
import { Project, TimesheetEntry, ProjectExpense, ProjectInvoice, ProjectTransaction } from './types';
import { initialProjects } from './mockProjects';

interface ProjectsContextType {
  projects: Project[];
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

const STORAGE_KEY = 'rooman_projects_state_v2';

const ProjectsContext = createContext<ProjectsContextType | undefined>(undefined);

export function ProjectsProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Project[]>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // Fallback
    }
    return initialProjects;
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(projects));
    } catch {
      // ignore
    }
  }, [projects]);

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
    const newId = `PRJ-${Math.floor(100 + Math.random() * 900)}`;
    const newProject: Project = {
      id: newId,
      ...data,
      billed: 0,
      expenses: 0,
      projectManager: 'Akshata Rathod',
      timesheets: [],
      expenseList: [],
      invoices: [],
      payments: [],
      transactions: [],
    };
    setProjects((prev) => [newProject, ...prev]);
    return newProject;
  };

  const updateProject = (id: string, updates: Partial<Project>) => {
    setProjects((prev) =>
      prev.map((p) => (p.id === id ? { ...p, ...updates } : p))
    );
  };

  const deleteProject = (id: string) => {
    setProjects((prev) => prev.filter((p) => p.id !== id));
  };

  const duplicateProject = (id: string): Project => {
    const source = projects.find((p) => p.id === id);
    const newId = `PRJ-${Math.floor(100 + Math.random() * 900)}`;
    const copy: Project = {
      ...(source || initialProjects[0]),
      id: newId,
      name: `${source ? source.name : 'New Project'} (Copy)`,
      status: 'draft',
      billed: 0,
      expenses: 0,
      timesheets: [],
      expenseList: [],
      invoices: [],
      payments: [],
      transactions: [],
    };
    setProjects((prev) => [copy, ...prev]);
    return copy;
  };

  const markAsCompleted = (id: string) => {
    setProjects((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: 'completed' as const } : p))
    );
  };

  const addTimesheet = (
    projectId: string,
    entry: Omit<TimesheetEntry, 'id' | 'projectId'>
  ) => {
    setProjects((prev) =>
      prev.map((p) => {
        if (p.id !== projectId) return p;
        const newEntry: TimesheetEntry = {
          id: `TS-${Date.now().toString().slice(-4)}`,
          projectId,
          ...entry,
        };
        return {
          ...p,
          timesheets: [newEntry, ...(p.timesheets || [])],
        };
      })
    );
  };

  const addExpense = (
    projectId: string,
    expense: Omit<ProjectExpense, 'id' | 'projectId'>
  ) => {
    setProjects((prev) =>
      prev.map((p) => {
        if (p.id !== projectId) return p;
        const newExp: ProjectExpense = {
          id: `EXP-${Date.now().toString().slice(-4)}`,
          projectId,
          ...expense,
        };
        const updatedExpenses = p.expenses + expense.amount;
        return {
          ...p,
          expenses: updatedExpenses,
          expenseList: [newExp, ...(p.expenseList || [])],
        };
      })
    );
  };

  const addInvoice = (
    projectId: string,
    invoice: Omit<ProjectInvoice, 'id' | 'projectId'>
  ) => {
    setProjects((prev) =>
      prev.map((p) => {
        if (p.id !== projectId) return p;
        const invNumber = invoice.invoiceNumber || `INV-2026-${Date.now().toString().slice(-4)}`;
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
        const updatedBilled = p.billed + invoice.amount;
        return {
          ...p,
          billed: updatedBilled,
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
