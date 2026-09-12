import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiService, VersionListItem } from './api.service';

@Component({
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <h2>公示版本</h2>
    <table>
      <thead><tr>
        <th>合同</th><th>版本</th><th>状态</th><th>受益范围</th><th>分配合计</th><th>未分配结余</th><th>公示时间</th><th></th>
      </tr></thead>
      <tbody>
        <tr *ngFor="let v of versions">
          <td>{{ v.contract_name }}</td>
          <td>v{{ v.version_no }}</td>
          <td><span class="badge" [ngClass]="v.status">{{ v.status_display }}</span></td>
          <td>{{ v.scope_display }}<span *ngIf="v.building_names.length">:{{ v.building_names.join('、') }}</span></td>
          <td>¥{{ v.allocated_total }}</td>
          <td><span [class.remainder]="+v.unallocated_amount > 0">¥{{ v.unallocated_amount }}</span></td>
          <td>{{ v.published_at ? (v.published_at | date:'yyyy-MM-dd HH:mm') : '—' }}</td>
          <td><a [routerLink]="['/versions', v.id]">明细 / 追溯</a></td>
        </tr>
      </tbody>
    </table>
  `,
})
export class VersionListComponent implements OnInit {
  private api = inject(ApiService);
  versions: VersionListItem[] = [];
  ngOnInit() { this.api.versions().subscribe((vs) => (this.versions = vs)); }
}
