import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Project, ProjectStatus, BillingMethod } from '../types';
import { formatINR } from '../mockProjects';
import { Badge } from '../../../components/common/Badge';
import {
  MoreVertical,
  Eye,
  Edit2,
  Copy,
  CheckCircle2,
  Trash2,
  Building2,
  Clock,
  Calendar,
} from 'lucide-react';

interface ProjectTableProps {
  projects: Project[];
  viewMode: 'list' | 'card';
  onEdit: (project: Project) => void;
  onDuplicate: (projectId: string) => void;
  onMarkCompleted: (projectId: string) => void;
  onDeleteRequest: (project: Project) => void;
}

export function getStatusBadge(status: ProjectStatus) {
  switch (status) {
    case 'active':
      return <Badge variant="success" size="sm" dot>Active</Badge>;
    case 'completed':
      return <Badge variant="primary" size="sm" dot>Completed</Badge>;
    case 'on_hold':
      return <Badge variant="warning" size="sm" dot>On Hold</Badge>;
    case 'draft':
      return <Badge variant="neutral" size="sm">Draft</Badge>;
    case 'cancelled':
      return <Badge variant="danger" size="sm">Cancelled</Badge>;
    default:
      return <Badge variant="neutral" size="sm">{status}</Badge>;
  }
}

export function getBillingMethodLabel(method: BillingMethod): string {
  switch (method) {
    case 'fixed_price':
      return 'Fixed Cost';
    case 'time_and_material':
      return 'Time & Material';
    case 'non_billable':
      return 'Non-Billable';
    default:
      return method;
  }
}

export function formatDate(dateString: string): string {
  if (!dateString) return '—';
  try {
    const d = new Date(dateString);
    return d.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return dateString;
  }
}

export function ProjectTable({
  projects,
  viewMode,
  onEdit,
  onDuplicate,
  onMarkCompleted,
  onDeleteRequest,
}: ProjectTableProps) {
  const navigate = useNavigate();
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close actions menu on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setActiveMenuId(null);
      }
    }
    if (activeMenuId) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [activeMenuId]);

  if (viewMode === 'card') {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects.map((project) => {
          const totalHours = (project.timesheets || []).reduce((acc, t) => acc + t.hours, 0);
          const unbilledAmount = Math.max(0, project.budget - project.billed);

          return (
            <div
              key={project.id}
              onClick={() => navigate(`/projects/${project.id}`)}
              className="bg-white rounded-xl border border-slate-200/90 shadow-2xs hover:border-brand-300 hover:shadow-card transition-all p-4 flex flex-col justify-between cursor-pointer group relative"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <span className="font-mono text-[10px] text-slate-400 uppercase tracking-wider block">
                      {project.id}
                    </span>
                    <h3 className="font-semibold text-sm text-slate-900 group-hover:text-brand-600 transition-colors truncate">
                      {project.name}
                    </h3>
                    <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5 truncate">
                      <Building2 className="w-3 h-3 text-slate-400 shrink-0" />
                      <span className="truncate">{project.customer}</span>
                    </p>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {getStatusBadge(project.status)}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setActiveMenuId(activeMenuId === project.id ? null : project.id);
                      }}
                      className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                    >
                      <MoreVertical className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className="mt-3.5 pt-3 border-t border-slate-100 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase font-medium block">
                      Billing Method
                    </span>
                    <span className="font-medium text-slate-800">
                      {getBillingMethodLabel(project.billingMethod)}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-400 uppercase font-medium block">
                      Billable Hours
                    </span>
                    <span className="font-medium text-slate-800 flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-400" />
                      {totalHours} hrs
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-400 uppercase font-medium block">
                      Total Budget
                    </span>
                    <span className="font-semibold text-slate-900">
                      {formatINR(project.budget)}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-400 uppercase font-medium block">
                      Unbilled Amount
                    </span>
                    <span className="font-semibold text-blue-700">
                      {formatINR(unbilledAmount)}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                <span className="flex items-center gap-1">
                  <Calendar className="w-3 h-3" />
                  {formatDate(project.startDate)} – {formatDate(project.endDate)}
                </span>
                <span className="text-brand-600 font-semibold group-hover:underline">
                  View →
                </span>
              </div>

              {/* Card Actions Menu */}
              {activeMenuId === project.id && (
                <div
                  ref={menuRef}
                  onClick={(e) => e.stopPropagation()}
                  className="absolute right-3 top-10 w-44 bg-white border border-slate-200 rounded-xl shadow-lg p-1 z-30 animate-in fade-in zoom-in-95 duration-100 text-left"
                >
                  <button
                    type="button"
                    onClick={() => {
                      setActiveMenuId(null);
                      navigate(`/projects/${project.id}`);
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 hover:text-brand-600 rounded-lg transition-colors cursor-pointer"
                  >
                    <Eye className="w-3.5 h-3.5 text-slate-400" />
                    <span>View Project</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setActiveMenuId(null);
                      onEdit(project);
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 hover:text-brand-600 rounded-lg transition-colors cursor-pointer"
                  >
                    <Edit2 className="w-3.5 h-3.5 text-slate-400" />
                    <span>Edit Project</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setActiveMenuId(null);
                      onDuplicate(project.id);
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 hover:text-brand-600 rounded-lg transition-colors cursor-pointer"
                  >
                    <Copy className="w-3.5 h-3.5 text-slate-400" />
                    <span>Duplicate</span>
                  </button>

                  {project.status !== 'completed' && (
                    <button
                      type="button"
                      onClick={() => {
                        setActiveMenuId(null);
                        onMarkCompleted(project.id);
                      }}
                      className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-emerald-700 hover:bg-emerald-50 rounded-lg transition-colors cursor-pointer"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      <span>Mark Completed</span>
                    </button>
                  )}

                  <div className="border-t border-slate-100 my-1" />

                  <button
                    type="button"
                    onClick={() => {
                      setActiveMenuId(null);
                      onDeleteRequest(project);
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-rose-600 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Delete</span>
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50/80 border-b border-slate-200 text-slate-500 uppercase tracking-wider font-semibold text-[10.5px]">
            <tr>
              <th className="py-3 px-4">Project</th>
              <th className="py-3 px-3">Customer</th>
              <th className="py-3 px-3">Billing Method</th>
              <th className="py-3 px-3">Status</th>
              <th className="py-3 px-3">Start Date</th>
              <th className="py-3 px-3">End Date</th>
              <th className="py-3 px-3 text-right">Budget</th>
              <th className="py-3 px-3 text-center w-12">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {projects.map((project) => (
              <tr
                key={project.id}
                onClick={() => navigate(`/projects/${project.id}`)}
                className="hover:bg-blue-50/40 transition-colors cursor-pointer group select-none"
              >
                {/* Project Name & Code */}
                <td className="py-3.5 px-4 min-w-[220px]">
                  <div className="font-semibold text-slate-900 group-hover:text-brand-600 transition-colors">
                    {project.name}
                  </div>
                  <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                    {project.id}
                  </div>
                </td>

                {/* Customer */}
                <td className="py-3.5 px-3 min-w-[180px]">
                  <div className="font-medium text-slate-800 truncate">
                    {project.customer}
                  </div>
                </td>

                {/* Billing Method */}
                <td className="py-3.5 px-3 whitespace-nowrap text-slate-700">
                  <span className="font-medium">
                    {getBillingMethodLabel(project.billingMethod)}
                  </span>
                </td>

                {/* Status */}
                <td className="py-3.5 px-3 whitespace-nowrap">
                  {getStatusBadge(project.status)}
                </td>

                {/* Start Date */}
                <td className="py-3.5 px-3 text-slate-600 whitespace-nowrap tabular-nums">
                  {formatDate(project.startDate)}
                </td>

                {/* End Date */}
                <td className="py-3.5 px-3 text-slate-600 whitespace-nowrap tabular-nums">
                  {formatDate(project.endDate)}
                </td>

                {/* Budget */}
                <td className="py-3.5 px-3 text-right font-medium text-slate-900 tabular-nums whitespace-nowrap">
                  {formatINR(project.budget)}
                </td>

                {/* Row Actions Menu */}
                <td
                  className="py-3.5 px-3 text-center relative"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    onClick={() =>
                      setActiveMenuId(
                        activeMenuId === project.id ? null : project.id
                      )
                    }
                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                    aria-label="Actions"
                  >
                    <MoreVertical className="w-4 h-4" />
                  </button>

                  {activeMenuId === project.id && (
                    <div
                      ref={menuRef}
                      className="absolute right-3 top-10 w-44 bg-white border border-slate-200 rounded-xl shadow-lg p-1 z-30 animate-in fade-in zoom-in-95 duration-100 text-left"
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setActiveMenuId(null);
                          navigate(`/projects/${project.id}`);
                        }}
                        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 hover:text-brand-600 rounded-lg transition-colors cursor-pointer"
                      >
                        <Eye className="w-3.5 h-3.5 text-slate-400" />
                        <span>View Project</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setActiveMenuId(null);
                          onEdit(project);
                        }}
                        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 hover:text-brand-600 rounded-lg transition-colors cursor-pointer"
                      >
                        <Edit2 className="w-3.5 h-3.5 text-slate-400" />
                        <span>Edit Project</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setActiveMenuId(null);
                          onDuplicate(project.id);
                        }}
                        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-slate-700 hover:bg-slate-50 hover:text-brand-600 rounded-lg transition-colors cursor-pointer"
                      >
                        <Copy className="w-3.5 h-3.5 text-slate-400" />
                        <span>Duplicate</span>
                      </button>

                      {project.status !== 'completed' && (
                        <button
                          type="button"
                          onClick={() => {
                            setActiveMenuId(null);
                            onMarkCompleted(project.id);
                          }}
                          className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-emerald-700 hover:bg-emerald-50 rounded-lg transition-colors cursor-pointer"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                          <span>Mark Completed</span>
                        </button>
                      )}

                      <div className="border-t border-slate-100 my-1" />

                      <button
                        type="button"
                        onClick={() => {
                          setActiveMenuId(null);
                          onDeleteRequest(project);
                        }}
                        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs text-rose-600 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Delete</span>
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
