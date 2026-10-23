import { useState, useMemo, useRef, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useProjects, type ProjectFormData } from './ProjectsContext';
import type { ProjectInvoiceInput } from '../../services/projectService';
import type { TimesheetEntry, ProjectExpense } from './types';
import { ProjectOverview } from './components/ProjectOverview';
import { ProjectTimesheets } from './components/ProjectTimesheets';
import { ProjectExpenses } from './components/ProjectExpenses';
import { ProjectTransactions } from './components/ProjectTransactions';
import { ProjectFormModal } from './components/ProjectFormModal';
import { LogTimeModal } from './components/LogTimeModal';
import { CreateInvoiceModal } from './components/CreateInvoiceModal';
import { DeleteConfirmModal } from './components/DeleteConfirmModal';
import { getStatusBadge, getBillingMethodLabel, formatDate } from './components/ProjectTable';
import { formatINR } from './format';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import {
  ArrowLeft,
  Clock,
  Plus,
  FileText,
  Receipt,
  MoreVertical,
  CheckCircle2,
  Edit2,
  Copy,
  Trash2,
  PieChart,
  Briefcase,
} from 'lucide-react';

type ProjectTab = 'overview' | 'timesheets' | 'expenses' | 'transactions';

export function ProjectDetailsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const {
    getProject,
    loadProject,
    updateProject,
    deleteProject,
    duplicateProject,
    markAsCompleted,
    addTimesheet,
    addExpense,
    addInvoice,
    projects,
  } = useProjects();
  const { showToast } = useToast();

  const [activeTab, setActiveTab] = useState<ProjectTab>('overview');
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isLogTimeOpen, setIsLogTimeOpen] = useState(false);
  const [isNewInvoiceOpen, setIsNewInvoiceOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(true);
  const moreMenuRef = useRef<HTMLDivElement>(null);

  // The list only carries summaries; fetch this project's detail (timesheets,
  // expenses, invoices, payments) when the page opens.
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setDetailLoading(true);
    loadProject(projectId).finally(() => {
      if (!cancelled) setDetailLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [projectId, loadProject]);

  // Close more menu on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (moreMenuRef.current && !moreMenuRef.current.contains(event.target as Node)) {
        setIsMoreMenuOpen(false);
      }
    }
    if (isMoreMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isMoreMenuOpen]);

  const project = useMemo(() => {
    return projectId ? getProject(projectId) : undefined;
  }, [projectId, getProject, projects]);

  const customerOptions = useMemo(() => {
    const list = Array.from(new Set(projects.map((p) => p.customer)));
    return list.sort();
  }, [projects]);

  if (!project && detailLoading) {
    return (
      <div className="p-6 sm:p-12 max-w-4xl mx-auto text-center text-xs text-slate-500">
        Loading project…
      </div>
    );
  }

  if (!project) {
    return (
      <div className="p-6 sm:p-12 max-w-4xl mx-auto text-center">
        <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto mb-3">
          <Briefcase className="w-6 h-6" />
        </div>
        <h2 className="text-xl font-bold text-slate-900">Project Not Found</h2>
        <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
          The requested project ID <code className="text-slate-800 font-mono">{projectId}</code> does not exist or has been removed.
        </p>
        <div className="mt-6">
          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate('/projects')}
            leadingIcon={<ArrowLeft className="w-4 h-4" />}
          >
            Back to Projects
          </Button>
        </div>
      </div>
    );
  }

  const unbilledAmount = Math.max(0, project.budget - project.billed);

  // Every action awaits the API; the context toasts failures and rolls back.
  const handleEditSubmit = async (data: ProjectFormData) => {
    if (await updateProject(project.id, data)) {
      showToast('success', 'Project Updated', `"${data.name}" has been updated.`);
      setIsEditModalOpen(false);
    }
  };

  const handleComplete = async () => {
    if (await markAsCompleted(project.id)) {
      showToast('success', 'Status Updated', 'Project marked as Completed.');
    }
  };

  const handleDuplicate = async () => {
    const clone = await duplicateProject(project.id);
    if (!clone) return;
    showToast('info', 'Project Duplicated', `Created draft clone: "${clone.name}".`);
    navigate(`/projects/${clone.id}`);
  };

  const handleDeleteConfirm = async () => {
    const name = project.name;
    setIsDeleteModalOpen(false);
    if (await deleteProject(project.id)) {
      showToast('info', 'Project Deleted', `"${name}" has been removed.`);
      navigate('/projects');
    }
  };

  const handleLogTime = async (entry: Omit<TimesheetEntry, 'id' | 'projectId'>) => {
    const ok = await addTimesheet(project.id, entry);
    if (ok) showToast('success', 'Time Logged', `${entry.hours} hrs logged.`);
    return ok;
  };

  const handleAddExpense = async (expense: Omit<ProjectExpense, 'id' | 'projectId'>) => {
    const ok = await addExpense(project.id, expense);
    if (ok) showToast('success', 'Expense Recorded', `"${expense.title}" added to project ledger.`);
    return ok;
  };

  const handleCreateInvoice = async (input: ProjectInvoiceInput) => {
    const created = await addInvoice(project.id, input);
    if (created) {
      showToast('success', 'Invoice Created', `Draft invoice ${created.invoiceNumber} created.`);
    }
    return Boolean(created);
  };

  const tabs: { key: ProjectTab; label: string; icon: React.ComponentType<{ className?: string }>; count?: number }[] = [
    { key: 'overview', label: 'Overview', icon: PieChart },
    { key: 'timesheets', label: 'Timesheets', icon: Clock, count: project.timesheets?.length || 0 },
    { key: 'expenses', label: 'Expenses', icon: Receipt, count: project.expenseList?.length || 0 },
    { key: 'transactions', label: 'Transactions', icon: FileText, count: project.transactions?.length || 0 },
  ];

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header with Breadcrumb and Actions */}
      <div className="space-y-3">
        <div>
          <Link
            to="/projects"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-600 hover:text-brand-700 transition-colors cursor-pointer group"
          >
            <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-0.5 transition-transform" />
            <span>Projects</span>
          </Link>
        </div>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
                {project.name}
              </h1>
              {getStatusBadge(project.status)}
            </div>

            <p className="text-xs text-slate-600 flex items-center gap-2 mt-1">
              <span className="font-semibold text-slate-800">{project.customer}</span>
              <span className="text-slate-300">•</span>
              <span className="text-slate-500 font-medium">{getBillingMethodLabel(project.billingMethod)}</span>
              <span className="text-slate-300">•</span>
              <span className="font-mono text-slate-400">{project.id}</span>
            </p>
          </div>

          {/* Primary Billing Actions */}
          <div className="flex items-center gap-2 shrink-0 relative">
            <Button
              variant="outline"
              size="sm"
              leadingIcon={<Clock className="w-3.5 h-3.5 text-slate-500" />}
              onClick={() => setIsLogTimeOpen(true)}
            >
              Log Time
            </Button>

            <Button
              variant="primary"
              size="sm"
              leadingIcon={<Plus className="w-3.5 h-3.5" />}
              onClick={() => setIsNewInvoiceOpen(true)}
            >
              New Invoice
            </Button>

            {/* More Menu Dropdown */}
            <div className="relative" ref={moreMenuRef}>
              <Button
                variant="outline"
                size="sm"
                className="px-2"
                onClick={() => setIsMoreMenuOpen((prev) => !prev)}
                title="More project actions"
              >
                <MoreVertical className="w-4 h-4" />
              </Button>

              {isMoreMenuOpen && (
                <div className="absolute right-0 top-10 w-44 bg-white border border-slate-200 rounded-xl shadow-lg p-1 z-30 animate-in fade-in zoom-in-95 duration-100 text-left">
                  <button
                    type="button"
                    onClick={() => {
                      setIsMoreMenuOpen(false);
                      setIsEditModalOpen(true);
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 hover:text-brand-600 rounded-lg transition-colors cursor-pointer"
                  >
                    <Edit2 className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span>Edit Project</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setIsMoreMenuOpen(false);
                      handleDuplicate();
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 hover:text-brand-600 rounded-lg transition-colors cursor-pointer"
                  >
                    <Copy className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span>Duplicate</span>
                  </button>

                  {project.status !== 'completed' && (
                    <button
                      type="button"
                      onClick={() => {
                        setIsMoreMenuOpen(false);
                        handleComplete();
                      }}
                      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-emerald-700 hover:bg-emerald-50 rounded-lg transition-colors cursor-pointer"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                      <span>Mark Completed</span>
                    </button>
                  )}

                  <div className="border-t border-slate-100 my-1" />

                  <button
                    type="button"
                    onClick={() => {
                      setIsMoreMenuOpen(false);
                      setIsDeleteModalOpen(true);
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-rose-600 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Delete</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Top Banner: Project Info & Compact Billing Summary */}
      <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
        <div>
          <span className="text-[10px] uppercase font-semibold text-slate-400 block">
            Billing Method
          </span>
          <span className="font-semibold text-slate-800 text-sm mt-0.5 block">
            {getBillingMethodLabel(project.billingMethod)}
          </span>
          <span className="text-[11px] text-slate-500">
            {formatDate(project.startDate)} – {formatDate(project.endDate)}
          </span>
        </div>

        <div>
          <span className="text-[10px] uppercase font-semibold text-slate-400 block">
            Project Budget
          </span>
          <span className="font-bold text-slate-900 text-sm mt-0.5 block tabular-nums">
            {formatINR(project.budget)}
          </span>
          <span className="text-[11px] text-slate-500">Contract cap</span>
        </div>

        <div>
          <span className="text-[10px] uppercase font-semibold text-slate-400 block">
            Billed Revenue
          </span>
          <span className="font-bold text-emerald-700 text-sm mt-0.5 block tabular-nums">
            {formatINR(project.billed)}
          </span>
          <span className="text-[11px] text-slate-500">Invoiced to client</span>
        </div>

        <div>
          <span className="text-[10px] uppercase font-semibold text-slate-400 block">
            Unbilled Balance
          </span>
          <span className="font-bold text-blue-700 text-sm mt-0.5 block tabular-nums">
            {formatINR(unbilledAmount)}
          </span>
          <span className="text-[11px] text-slate-500">Available to draw down</span>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="border-b border-slate-200">
        <nav className="flex space-x-2 overflow-x-auto scrollbar-none" aria-label="Tabs">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isCurrent = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 py-2.5 px-3 text-xs font-semibold border-b-2 whitespace-nowrap transition-colors cursor-pointer select-none ${
                  isCurrent
                    ? 'border-brand-600 text-brand-600'
                    : 'border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 ${isCurrent ? 'text-brand-600' : 'text-slate-400'}`} />
                <span>{tab.label}</span>
                {tab.count !== undefined && (
                  <span
                    className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                      isCurrent
                        ? 'bg-blue-100 text-brand-700'
                        : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab Panes */}
      <div>
        {activeTab === 'overview' && <ProjectOverview project={project} />}

        {activeTab === 'timesheets' && (
          <ProjectTimesheets project={project} onLogTime={handleLogTime} />
        )}

        {activeTab === 'expenses' && (
          <ProjectExpenses project={project} onAddExpense={handleAddExpense} />
        )}

        {activeTab === 'transactions' && (
          <ProjectTransactions project={project} onCreateInvoice={handleCreateInvoice} />
        )}
      </div>

      {/* Edit Project Modal */}
      <ProjectFormModal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        onSubmit={handleEditSubmit}
        initialProject={project}
        customerSuggestions={customerOptions}
      />

      {/* Quick Log Time Modal */}
      <LogTimeModal
        isOpen={isLogTimeOpen}
        onClose={() => setIsLogTimeOpen(false)}
        onLogTime={handleLogTime}
      />

      {/* Quick Invoice Modal */}
      <CreateInvoiceModal
        isOpen={isNewInvoiceOpen}
        onClose={() => setIsNewInvoiceOpen(false)}
        onCreateInvoice={handleCreateInvoice}
        defaultAmount={unbilledAmount}
      />

      {/* Delete Confirmation Modal */}
      <DeleteConfirmModal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={handleDeleteConfirm}
        project={project}
      />
    </div>
  );
}
