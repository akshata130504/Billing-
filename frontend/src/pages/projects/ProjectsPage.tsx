import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProjects, type ProjectFormData } from './ProjectsContext';
import { Project, ProjectFilterState } from './types';
import { ProjectSummaryCards } from './components/ProjectSummaryCards';
import { ProjectFilters } from './components/ProjectFilters';
import { ProjectTable } from './components/ProjectTable';
import { ProjectFormModal } from './components/ProjectFormModal';
import { DeleteConfirmModal } from './components/DeleteConfirmModal';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { Plus, Briefcase, Search } from 'lucide-react';
import { usePageSpec } from '../../appUi/usePageSpec';

export function ProjectsPage() {
  const ui = usePageSpec('projects');
  const {
    projects,
    addProject,
    updateProject,
    deleteProject,
    duplicateProject,
    markAsCompleted,
  } = useProjects();
  const { showToast } = useToast();
  const navigate = useNavigate();

  // Filters State
  const [filters, setFilters] = useState<ProjectFilterState>({
    searchQuery: '',
    statusTab: 'all',
    customer: 'all',
    viewMode: 'list',
  });

  // Modal States
  const [isFormModalOpen, setIsFormModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [deletingProject, setDeletingProject] = useState<Project | null>(null);

  // Extract unique customer options
  const customerOptions = useMemo(() => {
    const list = Array.from(new Set(projects.map((p) => p.customer)));
    return list.sort();
  }, [projects]);

  // Filtered Projects List
  const filteredProjects = useMemo(() => {
    return projects.filter((project) => {
      // Search matching name, customer, or ID
      if (filters.searchQuery.trim()) {
        const q = filters.searchQuery.toLowerCase();
        const matchesName = project.name.toLowerCase().includes(q);
        const matchesCustomer = project.customer.toLowerCase().includes(q);
        const matchesId = project.id.toLowerCase().includes(q);
        if (!matchesName && !matchesCustomer && !matchesId) return false;
      }

      // Status Quick Tab: All | Active | Inactive
      if (filters.statusTab === 'active' && project.status !== 'active') {
        return false;
      }
      if (filters.statusTab === 'inactive' && project.status === 'active') {
        return false;
      }

      // Customer filter
      if (filters.customer !== 'all' && project.customer !== filters.customer) {
        return false;
      }

      return true;
    });
  }, [projects, filters]);

  const handleFilterChange = (updates: Partial<ProjectFilterState>) => {
    setFilters((prev) => ({ ...prev, ...updates }));
  };

  const handleClearFilters = () => {
    setFilters({
      searchQuery: '',
      statusTab: 'all',
      customer: 'all',
      viewMode: filters.viewMode,
    });
  };

  const handleCreateNew = () => {
    setEditingProject(null);
    setIsFormModalOpen(true);
  };

  const handleEdit = (project: Project) => {
    setEditingProject(project);
    setIsFormModalOpen(true);
  };

  // Each handler awaits the server; failures are toasted by the context and the modal stays open.
  const handleFormSubmit = async (data: ProjectFormData) => {
    if (editingProject) {
      const ok = await updateProject(editingProject.id, data);
      if (!ok) return;
      showToast('success', 'Project Updated', `"${data.name}" has been updated.`);
    } else {
      const created = await addProject(data);
      if (!created) return;
      showToast('success', 'Project Created', `"${created.name}" created.`);
    }
    setIsFormModalOpen(false);
    setEditingProject(null);
  };

  const handleDuplicate = async (projectId: string) => {
    const duplicated = await duplicateProject(projectId);
    if (!duplicated) return;
    showToast('info', 'Project Duplicated', `Created draft clone: "${duplicated.name}".`);
    navigate(`/projects/${duplicated.id}`);
  };

  const handleMarkCompleted = async (projectId: string) => {
    if (await markAsCompleted(projectId)) {
      showToast('success', 'Status Updated', 'Project marked as Completed.');
    }
  };

  const handleDeleteConfirm = async () => {
    if (deletingProject) {
      const target = deletingProject;
      setDeletingProject(null);
      if (await deleteProject(target.id)) {
        showToast('info', 'Project Deleted', `"${target.name}" has been removed.`);
      }
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-5">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4" {...ui.edit('header')}>
        <div>
          <div className="flex items-center gap-2 mb-1 text-xs text-slate-500 font-medium">
            <span>{ui.text('header', 'eyebrow')}</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5">
            <Briefcase className="w-6 h-6 text-brand-600 shrink-0" />
            <span>{ui.text('header', 'title')}</span>
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 mt-1 max-w-2xl leading-relaxed">
            {ui.text('header', 'subtitle')}
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <Button
            variant="primary"
            size="md"
            leadingIcon={<Plus className="w-4 h-4" />}
            onClick={handleCreateNew}
          >
            New Project
          </Button>
        </div>
      </div>

      {/* Compact Financial Summary Strip (Calm and non-dominant) */}
      <ProjectSummaryCards projects={projects} />

      {/* Filter and Search Bar with View Toggle */}
      <ProjectFilters
        filters={filters}
        onFilterChange={handleFilterChange}
        onClearFilters={handleClearFilters}
        customerOptions={customerOptions}
      />

      {/* Project Records List or Empty State */}
      {filteredProjects.length === 0 ? (
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs p-12 text-center" {...ui.edit('empty')}>
          <div className="w-12 h-12 rounded-full bg-blue-50 text-brand-600 flex items-center justify-center mx-auto mb-3">
            <Search className="w-6 h-6" />
          </div>
          <h3 className="text-base font-bold text-slate-900">
            {ui.text('empty', 'none')}
          </h3>
          <p className="text-xs text-slate-500 mt-1.5 max-w-sm mx-auto">
            Try adjusting your search query, status tabs, or selected customer.
          </p>
          <div className="mt-4">
            <Button variant="outline" size="sm" onClick={handleClearFilters}>
              Clear Filters
            </Button>
          </div>
        </div>
      ) : (
        <ProjectTable
          projects={filteredProjects}
          viewMode={filters.viewMode}
          onEdit={handleEdit}
          onDuplicate={handleDuplicate}
          onMarkCompleted={handleMarkCompleted}
          onDeleteRequest={(project) => setDeletingProject(project)}
        />
      )}

      {/* Modals */}
      <ProjectFormModal
        isOpen={isFormModalOpen}
        onClose={() => {
          setIsFormModalOpen(false);
          setEditingProject(null);
        }}
        onSubmit={handleFormSubmit}
        initialProject={editingProject}
        customerSuggestions={customerOptions}
      />

      <DeleteConfirmModal
        isOpen={Boolean(deletingProject)}
        onClose={() => setDeletingProject(null)}
        onConfirm={handleDeleteConfirm}
        project={deletingProject}
      />
    </div>
  );
}
