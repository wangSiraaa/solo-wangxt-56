import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiService, Contract } from './api.service';

@Component({
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <h2>收益合同</h2>
    <table>
      <thead><tr>
        <th>名称</th><th>来源</th><th>金额</th><th>归属期</th><th>收款日期</th><th>附件</th><th></th>
      </tr></thead>
      <tbody>
        <tr *ngFor="let c of contracts">
          <td>{{ c.name }}</td>
          <td>{{ c.source_type_display }}</td>
          <td>¥{{ c.total_amount }}</td>
          <td>{{ c.period_start }} ~ {{ c.period_end }}</td>
          <td>{{ c.received_date }}</td>
          <td>
            <span *ngIf="c.attachments.length; else none">{{ c.attachments.length }} 份</span>
            <ng-template #none><span class="remainder">缺失,不可公示</span></ng-template>
          </td>
          <td><a [routerLink]="['/contracts', c.id]">查看</a></td>
        </tr>
      </tbody>
    </table>
  `,
})
export class ContractListComponent implements OnInit {
  private api = inject(ApiService);
  contracts: Contract[] = [];
  ngOnInit() { this.api.contracts().subscribe((cs) => (this.contracts = cs)); }
}
